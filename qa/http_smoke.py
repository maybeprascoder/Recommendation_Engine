"""Exercise the running local server using disposable, synthetic repo fixtures.

Run with --keep-fixtures for manual browser checks, then --cleanup afterwards.
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "data/profiles/qa-readiness/profile.json"
PROGRAM = ROOT / "data/programs/qa-readiness.yaml"


def cleanup():
    for target in (PROFILE, PROGRAM):
        assert target.resolve().is_relative_to(ROOT / "data")
        if target.exists():
            target.unlink()
    if PROFILE.parent.exists():
        PROFILE.parent.rmdir()


def request(path, payload=None, host=None):
    headers = {"Content-Type": "application/json"}
    if host:
        headers["Host"] = host
    req = Request(
        "http://127.0.0.1:8000" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
    )
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def main():
    if "--cleanup" in sys.argv:
        cleanup()
        return
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRAM.parent.mkdir(parents=True, exist_ok=True)
    for dest, source in ((PROFILE, "profile.json"), (PROGRAM, "program.yaml")):
        with dest.open("x", encoding="utf-8") as stream:
            stream.write((ROOT / "tests/fixtures/cli" / source).read_text("utf-8"))
    selection = {
        "profile_path": PROFILE.relative_to(ROOT).as_posix(),
        "program_path": PROGRAM.relative_to(ROOT).as_posix(),
    }
    try:
        code, body = request("/review", selection)
        assert code == 200, body
        draft = json.loads(body)
        corrections = [
            {
                "evidence_id": item["id"],
                **{
                    key: item[key]
                    for key in (
                        "raw_text",
                        "kind",
                        "state",
                        "quality",
                        "depth",
                        "recency",
                    )
                },
            }
            for item in draft["profile"]["evidence"]
        ]
        code, body = request(
            "/confirm",
            {
                "review_id": draft["review_id"],
                "confirmed": True,
                "corrections": corrections,
            },
        )
        assert code == 200, body
        confirmed_selection = {"confirmation_id": json.loads(body)["confirmation_id"]}
        print("PASS review and explicit confirmation through real CLI")
        cases = [
            ("index", "/", None, None, 200),
            ("javascript", "/static/app.js", None, None, 200),
            ("styles", "/static/styles.css", None, None, 200),
            ("tokens", "/static/tokens.css", None, None, 200),
            ("profiles", "/profiles", None, None, 200),
            ("programs", "/programs", None, None, 200),
            ("bad host", "/", None, "untrusted.example", 400),
            ("missing fields", "/score", {}, None, 422),
            ("extra fields", "/score", {**selection, "extra": True}, None, 422),
            ("unconfirmed scoring", "/score", selection, None, 422),
            (
                "path traversal",
                "/review",
                {**selection, "profile_path": "../profile.json"},
                None,
                400,
            ),
            (
                "missing profile",
                "/review",
                {**selection, "profile_path": "data/profiles/missing/profile.json"},
                None,
                404,
            ),
            (
                "wrong suffix",
                "/review",
                {**selection, "program_path": "data/programs/other.txt"},
                None,
                400,
            ),
            ("real CLI scoring", "/score", confirmed_selection, None, 200),
        ]
        for name, endpoint, payload, host, expected in cases:
            code, body = request(endpoint, payload, host)
            assert code == expected, (name, code, body)
            print(f"PASS {name}: HTTP {code}")
            if name == "real CLI scoring":
                assessment = json.loads(body)
                (ROOT / "qa/live-assessment.json").write_bytes(body)
                assert len(assessment["report"]) == 6
                assert assessment["report"]["what_we_understand_about_you"]
                assert (
                    assessment["eligibility_result"]["status"]
                    == assessment["assessment"]["eligibility"]
                )
                assert assessment["eligibility_result"]["rule_breakdown"]
                print("Report present:", "report" in assessment)
                print(
                    "Eligibility breakdown present:", "eligibility_result" in assessment
                )
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(
                pool.map(lambda _: request("/score", confirmed_selection), range(8))
            )
        assert all(code == 200 for code, _ in responses)
        assert len({body for _, body in responses}) == 1
        elapsed = time.perf_counter() - start
        print(f"PASS 8 concurrent/repeated requests: byte-identical in {elapsed:.2f}s")
    finally:
        if "--keep-fixtures" not in sys.argv:
            cleanup()


if __name__ == "__main__":
    main()
