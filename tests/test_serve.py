"""Contract tests for the local CLI-backed scoring harness."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

import serve


def test_score_runs_the_real_installed_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch installation/import failures that a mocked subprocess cannot."""
    fixtures = Path(serve.__file__).parent / "tests" / "fixtures" / "cli"
    profile, program = _catalog_files(tmp_path)
    profile.write_bytes((fixtures / "profile.json").read_bytes())
    program.write_bytes((fixtures / "program.yaml").read_bytes())
    monkeypatch.setattr(serve, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(serve, "PROFILE_ROOT", profile.parent)
    monkeypatch.setattr(serve, "PROGRAM_ROOT", program.parent)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.setenv(
        "PATH",
        str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
    )
    draft_response = serve.review(
        serve.ReviewRequest(
            profile_path="data/profiles/profile.json",
            program_path="data/programs/program.yaml",
        )
    )
    assert draft_response.status_code == 200, draft_response.body.decode()
    draft = json.loads(draft_response.body)
    corrections = [
        {
            "evidence_id": e["id"],
            **{
                k: e[k]
                for k in ("raw_text", "kind", "state", "quality", "depth", "recency")
            },
        }
        for e in draft["profile"]["evidence"]
    ]
    confirmed = serve.confirm(
        serve.ConfirmRequest(
            review_id=draft["review_id"], confirmed=True, corrections=corrections
        )
    )
    assert confirmed.status_code == 200, confirmed.body.decode()
    response = serve.score(
        serve.ScoreRequest(
            confirmation_id=json.loads(confirmed.body)["confirmation_id"]
        )
    )
    assert response.status_code == 200, response.body.decode()
    payload = json.loads(response.body)
    audit = payload["assessment"]["audit"]
    assert audit["profile_snapshot"]["evidence"][0]["id"] == "ml-paper"
    assert audit["program_config_snapshot"]["program_id"] == "example-ml-ms"
    assert len(payload["report"]) == 6
    assert payload["report"]["strengths"][0]["evidence_ids"] == ["ml-paper"]
    assert (
        payload["eligibility_result"]["rule_breakdown"][0]["rule_id"] == "minimum-gpa"
    )


def test_index_and_static_assets_are_served() -> None:
    route_paths = {getattr(route, "path", None) for route in serve.app.routes}
    page = serve.index()
    tokens = serve.WEB_ROOT / "tokens.css"

    assert {"/", "/score", "/profiles", "/programs", "/static"} <= route_paths
    assert Path(page.path).name == "index.html"
    assert "UniHive scoring review" in Path(page.path).read_text(encoding="utf-8")
    assert "--band-emerging" in tokens.read_text(encoding="utf-8")


def test_catalogs_list_only_supported_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_root = tmp_path / "data" / "profiles"
    program_root = tmp_path / "data" / "programs"
    (profile_root / "case-a").mkdir(parents=True)
    program_root.mkdir(parents=True)
    (profile_root / "case-a" / "profile.json").write_text("{}", encoding="utf-8")
    (profile_root / "ignored.json").write_text("{}", encoding="utf-8")
    (program_root / "one.yaml").write_text("program_id: one", encoding="utf-8")
    (program_root / "ignored.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(serve, "PROJECT_ROOT", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve, "PROFILE_ROOT", profile_root)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve, "PROGRAM_ROOT", program_root)  # type: ignore[attr-defined]

    assert [option.model_dump() for option in serve.profiles()] == [
        {"path": "data/profiles/case-a/profile.json", "label": "case-a/profile.json"}
    ]
    assert [option.model_dump() for option in serve.programs()] == [
        {"path": "data/programs/one.yaml", "label": "one.yaml"}
    ]


def test_score_invokes_cli_and_preserves_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, program = _catalog_files(tmp_path)
    raw_assessment = b'{"pathway_readiness":"STRONG","not_assessed":[]}'
    captured: dict[str, object] = {}

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, raw_assessment, b"warning")

    monkeypatch.setattr(serve, "PROJECT_ROOT", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve, "PROFILE_ROOT", profile.parent)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve, "PROGRAM_ROOT", program.parent)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve.subprocess, "run", fake_run)  # type: ignore[attr-defined]

    confirmation_id = serve._save_record(
        "confirmations", {"program_path": str(program), "profile": {}}
    )
    response = serve.score(serve.ScoreRequest(confirmation_id=confirmation_id))

    assert response.status_code == 200
    assert response.body == raw_assessment
    assert captured["command"] == [
        "unihive",
        "--score-only",
        "--profile",
        "-",
        "--program",
        str(program),
        "--json",
        "--report",
    ]
    assert captured["kwargs"] == {
        "cwd": tmp_path,
        "capture_output": True,
        "check": False,
        "input": b"{}",
        "timeout": 30,
        "env": {**os.environ, "PYTHONUTF8": "1"},
    }


def test_score_returns_cli_stderr_as_structured_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, program = _catalog_files(tmp_path)

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 2, b"", b"invalid program\n")

    monkeypatch.setattr(serve, "PROJECT_ROOT", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve, "PROFILE_ROOT", profile.parent)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve, "PROGRAM_ROOT", program.parent)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve.subprocess, "run", fake_run)  # type: ignore[attr-defined]

    confirmation_id = serve._save_record(
        "confirmations", {"program_path": str(program), "profile": {}}
    )
    response = serve.score(serve.ScoreRequest(confirmation_id=confirmation_id))

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "error": {
            "code": "CLI_SCORE_FAILED",
            "message": "The UniHive CLI could not process this request.",
            "stderr": "invalid program",
            "return_code": 2,
        }
    }


def test_score_rejects_a_path_outside_the_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, program = _catalog_files(tmp_path)
    outside = tmp_path / "outside" / "profile.json"
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(serve, "PROJECT_ROOT", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve, "PROFILE_ROOT", profile.parent)  # type: ignore[attr-defined]
    monkeypatch.setattr(serve, "PROGRAM_ROOT", program.parent)  # type: ignore[attr-defined]

    with pytest.raises(HTTPException, match="outside its data directory") as caught:
        serve.review(
            serve.ReviewRequest(
                profile_path=str(outside),
                program_path="data/programs/program.yaml",
            )
        )

    assert caught.value.status_code == 400


def test_server_does_not_import_engine_modules() -> None:
    tree = ast.parse(Path(serve.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert not any(
        name == "unihive" or name.startswith("unihive.") for name in imported
    )


def _catalog_files(tmp_path: Path) -> tuple[Path, Path]:
    profile = tmp_path / "data" / "profiles" / "profile.json"
    program = tmp_path / "data" / "programs" / "program.yaml"
    profile.parent.mkdir(parents=True)
    program.parent.mkdir(parents=True)
    profile.write_text("{}", encoding="utf-8")
    program.write_text("program_id: test", encoding="utf-8")
    return profile, program
