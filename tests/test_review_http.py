"""Live HTTP tests using the installed CLI, without mocked subprocesses."""

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from understanding_samples import mixed_result

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    root = tmp_path_factory.mktemp("review-http")
    for name in ("profile.json", "program.yaml"):
        (root / name).write_bytes((ROOT / "tests/fixtures/cli" / name).read_bytes())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    code = (
        "import sys; from pathlib import Path; import serve, uvicorn; "
        "serve.PROJECT_ROOT = Path(sys.argv[1]); "
        "serve.PROFILE_ROOT = serve.PROJECT_ROOT; "
        "serve.PROGRAM_ROOT = serve.PROJECT_ROOT; "
        "uvicorn.run(serve.app, host='127.0.0.1', port=int(sys.argv[2]))"
    )
    env = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent)
        + os.pathsep
        + os.environ.get("PATH", ""),
    }
    with (root / "server.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(root), str(port)],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    with urlopen(base + "/profiles", timeout=1):
                        break
                except URLError:
                    if process.poll() is not None:
                        pytest.fail((root / "server.log").read_text())
                    time.sleep(0.1)
            else:
                pytest.fail("Server did not start")
            yield base, root
        finally:
            process.terminate()
            process.wait(timeout=10)


def post(base: str, endpoint: str, payload: dict) -> tuple[int, dict]:
    request = Request(
        base + endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def draft(base: str) -> tuple[dict, list[dict]]:
    code, body = post(
        base,
        "/review",
        {"profile_path": "profile.json", "program_path": "program.yaml"},
    )
    assert code == 200, body
    corrections = [
        {
            "evidence_id": item["id"],
            **{
                k: item[k]
                for k in ("raw_text", "kind", "state", "quality", "depth", "recency")
            },
        }
        for item in body["profile"]["evidence"]
    ]
    return body, corrections


def test_confirm_edit_score_and_replay(server: tuple[str, Path]) -> None:
    base, root = server
    before = (root / "profile.json").read_bytes()
    review, corrections = draft(base)
    corrections[0]["raw_text"] = "Corrected publication — 学生"
    corrections[0]["quality"] = "preprint"
    code, confirmed = post(
        base,
        "/confirm",
        {
            "review_id": review["review_id"],
            "confirmed": True,
            "corrections": corrections,
        },
    )
    assert code == 200, confirmed
    assert confirmed["profile"]["evidence"][0]["state"] == "SELF_REPORTED_PRESENT"
    assert (
        confirmed["profile"]["evidence"][0]["source"]
        == review["profile"]["evidence"][0]["source"]
    )
    selection = {"confirmation_id": confirmed["confirmation_id"]}
    code, scored = post(base, "/score", selection)
    assert code == 200, scored
    assert scored["assessment"]["audit"]["profile_snapshot"] == confirmed["profile"]
    assert (root / "profile.json").read_bytes() == before
    # A new confirmation cannot mutate the first snapshot.
    corrections[0]["state"] = "UNKNOWN"
    code, unknown = post(
        base,
        "/confirm",
        {
            "review_id": review["review_id"],
            "confirmed": True,
            "corrections": corrections,
        },
    )
    assert code == 200, unknown
    code, unknown_score = post(
        base, "/score", {"confirmation_id": unknown["confirmation_id"]}
    )
    assert code == 200, unknown_score
    assert unknown_score["assessment"]["pathway_readiness"] is None
    assert unknown_score["report"]["gaps"] == []
    assert post(base, "/score", selection)[1] == scored
    audit = root / "assessment.json"
    audit.write_text(json.dumps(scored), encoding="utf-8")
    replay = subprocess.run(
        [
            sys.executable,
            str(ROOT / "cli.py"),
            "replay",
            "--audit",
            str(audit),
            "--json",
            "--report",
        ],
        capture_output=True,
        env={**os.environ, "PYTHONUTF8": "1"},
        timeout=30,
    )
    assert replay.returncode == 0, replay.stderr.decode()
    assert json.loads(replay.stdout) == scored


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"profile_path": "profile.json", "program_path": "program.yaml"}, 422),
        ({"confirmation_id": "0" * 32}, 404),
        ({"confirmation_id": "../profile.json"}, 422),
        ({"confirmation_id": "0" * 32, "profile": {}}, 422),
    ],
)
def test_unconfirmed_scoring_is_rejected(
    server: tuple[str, Path], payload: dict, status: int
) -> None:
    assert post(server[0], "/score", payload)[0] == status


@pytest.mark.parametrize("value", [False, "true", 1])
def test_confirmation_cannot_be_coerced(
    server: tuple[str, Path], value: object
) -> None:
    review, corrections = draft(server[0])
    assert (
        post(
            server[0],
            "/confirm",
            {
                "review_id": review["review_id"],
                "confirmed": value,
                "corrections": corrections,
            },
        )[0]
        == 422
    )


def test_stale_source_and_draft_as_confirmation_rejected(
    server: tuple[str, Path],
) -> None:
    base, root = server
    review, corrections = draft(base)
    assert post(base, "/score", {"confirmation_id": review["review_id"]})[0] == 404
    original = (root / "profile.json").read_bytes()
    try:
        (root / "profile.json").write_bytes(original + b"\n")
        assert (
            post(
                base,
                "/confirm",
                {
                    "review_id": review["review_id"],
                    "confirmed": True,
                    "corrections": corrections,
                },
            )[0]
            == 409
        )
    finally:
        (root / "profile.json").write_bytes(original)


def test_profile_followup_continues_latest_snapshot_and_saves_answer(
    server: tuple[str, Path],
) -> None:
    base, root = server
    review, corrections = draft(base)
    details = {
        key: value for key, value in review["profile"].items() if key != "evidence"
    }
    details["normalized_gpa"] = "3.2"
    addition = {
        **corrections[0],
        "evidence_id": "new-project",
        "kind": "project",
        "raw_text": "Synthetic student project",
    }
    code, saved = post(
        base,
        "/confirm",
        {
            "review_id": review["review_id"],
            "confirmed": True,
            "corrections": corrections,
            "additions": [addition],
            "profile_details": details,
        },
    )
    assert code == 200, saved
    selection = {"confirmation_id": saved["confirmation_id"]}
    code, questions = post(base, "/questions", selection)
    assert code == 200, questions
    question = next(
        item
        for item in questions["questions"]
        if item["question"]["resolves_id"] == "constraints"
    )
    code, continued = post(
        base,
        "/continue-review",
        {**selection, "question_id": question["question"]["question_id"]},
    )
    assert code == 200, continued
    assert continued["profile"] == saved["profile"]
    assert continued["followup_question"] == question
    assert continued["profile"]["normalized_gpa"] == "3.2"
    assert continued["profile"]["evidence"][-1]["state"] == "SELF_REPORTED_PRESENT"
    details["constraints"] = ["Part-time study"]
    corrections = [
        {
            "evidence_id": item["id"],
            **{
                key: item[key]
                for key in ("raw_text", "kind", "state", "quality", "depth", "recency")
            },
        }
        for item in continued["profile"]["evidence"]
    ]
    code, answered = post(
        base,
        "/confirm",
        {
            "review_id": continued["review_id"],
            "confirmed": True,
            "corrections": corrections,
            "profile_details": details,
        },
    )
    assert code == 200, answered
    final_selection = {"confirmation_id": answered["confirmation_id"]}
    code, updated = post(base, "/score", final_selection)
    assert code == 200, updated
    assert updated["assessment"]["audit"]["profile_snapshot"] == answered["profile"]
    code, remaining = post(base, "/questions", final_selection)
    assert code == 200, remaining
    assert "constraints" not in [
        item["question"]["resolves_id"] for item in remaining["questions"]
    ]
    receipt = json.loads(
        (
            root / "data/reviews/confirmations" / f"{answered['confirmation_id']}.json"
        ).read_text()
    )
    assert receipt["parent_confirmation_id"] == saved["confirmation_id"]
    assert receipt["followup_question"] == question
    assert (
        post(
            base,
            "/continue-review",
            {**final_selection, "question_id": question["question"]["question_id"]},
        )[0]
        == 409
    )
    assert json.loads((root / "profile.json").read_text())["normalized_gpa"] != "3.2"


def test_interpretation_correction_confirmation_receipt_and_replay(
    server: tuple[str, Path],
) -> None:
    from unihive.understanding import canonical_json, fingerprint

    base, root = server
    result = mixed_result()
    original_profile = (root / "profile.json").read_bytes()
    code, review = post(
        base,
        "/review",
        {
            "profile_path": "profile.json",
            "program_path": "program.yaml",
            "understanding": result.model_dump(mode="json"),
        },
    )
    assert code == 200, review
    assert review["understanding"] == result.model_dump(mode="json")
    assert len(review["claim_corrections"]) == len(result.draft.claims)
    assert len(review["academic_corrections"]) == len(result.draft.academics)
    assert len(review["judgment_corrections"]) == len(result.draft.judgments)
    evidence_changes = [
        {
            "evidence_id": item["id"],
            **{
                key: item[key]
                for key in ("raw_text", "kind", "state", "quality", "depth", "recency")
            },
        }
        for item in review["profile"]["evidence"]
    ]
    claim_changes = review["claim_corrections"]
    academic_changes = review["academic_corrections"]
    judgment_changes = review["judgment_corrections"]
    for change in claim_changes:
        change["decision"] = "confirm"
    claim_changes[2].update(
        statement="Correction: the supervisor did this work, not me.",
        notes="Keep the publication judgment attached to the supervisor.",
    )
    submission = {
        "review_id": review["review_id"],
        "confirmed": True,
        "corrections": evidence_changes,
        "claim_corrections": claim_changes,
        "academic_corrections": academic_changes,
        "judgment_corrections": judgment_changes,
    }
    # Missing/duplicate reviews and client attempts to replace the interpretation fail.
    assert post(base, "/confirm", {**submission, "claim_corrections": []})[0] == 422
    assert post(base, "/confirm", {**submission, "understanding": {}})[0] == 422
    code, confirmed = post(base, "/confirm", submission)
    assert code == 200, confirmed
    selection = {"confirmation_id": confirmed["confirmation_id"]}
    code, receipt = post(base, "/receipt", selection)
    assert code == 200, receipt
    assert receipt["submission"]["understanding"] == result.model_dump(mode="json")
    assert receipt["submission"]["claim_corrections"] == claim_changes
    assert receipt["submission"]["academic_corrections"] == academic_changes
    assert receipt["submission"]["judgment_corrections"] == judgment_changes
    assert receipt["understanding_sha256"] == fingerprint(canonical_json(result))
    assert receipt["profile"] == confirmed["profile"]
    assert receipt["profile_sha256"] == fingerprint(
        json.dumps(confirmed["profile"], sort_keys=True, ensure_ascii=False)
    )
    imported = [
        item
        for item in confirmed["profile"]["evidence"]
        if item["scoring_exclusion"] is not None
    ]
    assert len(imported) == 2
    assert all(item["state"] == "SELF_REPORTED_PRESENT" for item in imported)
    assert confirmed["profile"]["normalized_gpa"] == review["profile"]["normalized_gpa"]
    projected_academic = confirmed["profile"]["academic_history"][-1]
    assert projected_academic["grade"] == "8.2"
    assert projected_academic["grade_scale"] == "10"
    assert "completed" not in projected_academic
    assert (root / "profile.json").read_bytes() == original_profile
    code, scored = post(base, "/score", selection)
    assert code == 200, scored
    assert scored["assessment"]["audit"]["profile_snapshot"] == confirmed["profile"]
    contributions = scored["assessment"]["audit"]["evidence_ids_used"]
    assert not set(item["id"] for item in imported).intersection(contributions)
    audit_path = root / "understanding-assessment.json"
    audit_path.write_text(json.dumps(scored), encoding="utf-8")
    replay = subprocess.run(
        [
            sys.executable,
            str(ROOT / "cli.py"),
            "replay",
            "--audit",
            str(audit_path),
            "--json",
            "--report",
        ],
        capture_output=True,
        env={**os.environ, "PYTHONUTF8": "1"},
        timeout=30,
    )
    assert replay.returncode == 0, replay.stderr.decode()
    assert json.loads(replay.stdout) == scored
    code, continued = post(base, "/continue-review", selection)
    assert code == 200, continued
    assert continued["understanding"] == review["understanding"]
    assert continued["claim_corrections"] == claim_changes
    assert continued["academic_corrections"] == academic_changes
    assert continued["judgment_corrections"] == judgment_changes
    evidence_changes = [
        {
            "evidence_id": item["id"],
            **{
                key: item[key]
                for key in ("raw_text", "kind", "state", "quality", "depth", "recency")
            },
        }
        for item in continued["profile"]["evidence"]
    ]
    claim_changes[0]["decision"] = "exclude"
    code, updated = post(
        base,
        "/confirm",
        {
            "review_id": continued["review_id"],
            "confirmed": True,
            "corrections": evidence_changes,
            "claim_corrections": claim_changes,
            "academic_corrections": academic_changes,
            "judgment_corrections": judgment_changes,
        },
    )
    assert code == 200, updated
    assert (
        len(updated["profile"]["evidence"]) == len(confirmed["profile"]["evidence"]) - 1
    )
    code, updated_receipt = post(
        base,
        "/receipt",
        {
            "confirmation_id": updated["confirmation_id"],
        },
    )
    assert code == 200, updated_receipt
    assert updated_receipt["parent_confirmation_id"] == confirmed["confirmation_id"]
    assert updated_receipt["submission"]["understanding"] == review["understanding"]
    assert post(base, "/receipt", selection)[1] == receipt
    assert post(base, "/score", selection)[1] == scored


def test_interpretation_import_rejects_forged_support_lists(
    server: tuple[str, Path],
) -> None:
    result = mixed_result().model_dump(mode="json")
    result["supported_claim_ids"].append("unsupported")
    code, response = post(
        server[0],
        "/review",
        {
            "profile_path": "profile.json",
            "program_path": "program.yaml",
            "understanding": result,
        },
    )
    assert code == 422, response


def test_context_and_absence_survive_confirmation_receipt_and_reopen(server):
    from test_understanding_context import analyze, recorded

    result = analyze(*recorded("I did not use ETABS.", "reported_absent", "ETABS"))
    base, _ = server
    code, review = post(
        base,
        "/review",
        {
            "profile_path": "profile.json",
            "program_path": "program.yaml",
            "understanding": result.model_dump(mode="json"),
        },
    )
    assert code == 200, review
    assert review["claim_corrections"][0]["presence"] == "reported_absent"
    corrections = [
        {
            "evidence_id": item["id"],
            **{
                key: item[key]
                for key in ("raw_text", "kind", "state", "quality", "depth", "recency")
            },
        }
        for item in review["profile"]["evidence"]
    ]
    code, confirmed = post(
        base,
        "/confirm",
        {
            "review_id": review["review_id"],
            "confirmed": True,
            "corrections": corrections,
            "claim_corrections": review["claim_corrections"],
            "academic_corrections": review["academic_corrections"],
            "judgment_corrections": review["judgment_corrections"],
        },
    )
    assert code == 200, confirmed
    imported = [
        e for e in confirmed["profile"]["evidence"] if e["source_claim_id"] == "c1"
    ]
    assert len(imported) == 1 and imported[0]["state"] == "CONFIRMED_ABSENT"
    selection = {"confirmation_id": confirmed["confirmation_id"]}
    code, receipt = post(base, "/receipt", selection)
    assert code == 200, receipt
    assert receipt["submission"]["understanding"] == result.model_dump(mode="json")
    code, continued = post(base, "/continue-review", selection)
    assert code == 200, continued
    assert continued["understanding"]["supported_context_ids"] == ["t1"]
    assert continued["claim_corrections"][0]["presence"] == "reported_absent"
    code, scored = post(base, "/score", selection)
    assert code == 200, scored
    assert imported[0]["id"] not in scored["assessment"]["audit"]["evidence_ids_used"]
