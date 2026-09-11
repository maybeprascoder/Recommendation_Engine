"""Local-only HTTP wrapper around the canonical UniHive CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "web"
PROFILE_ROOT = PROJECT_ROOT / "data" / "profiles"
PROGRAM_ROOT = PROJECT_ROOT / "data" / "programs"
DEMO_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "cli"


class ReviewRequest(BaseModel):
    """Paths selected from the local profile and program catalogs."""

    model_config = ConfigDict(extra="forbid")

    profile_path: str
    program_path: str
    understanding: dict[str, JsonValue] | None = None


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    confirmed: StrictBool
    corrections: list[dict[str, JsonValue]]
    profile_details: dict[str, JsonValue] | None = None
    additions: list[dict[str, JsonValue]] = Field(default_factory=list)
    claim_corrections: list[dict[str, JsonValue]] = Field(default_factory=list)


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class ContinueRequest(ScoreRequest):
    question_id: str | None = None


class FileOption(BaseModel):
    """A local data file available to the review harness."""

    path: str
    label: str


app = FastAPI(
    title="UniHive scoring review",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "[::1]"],
)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single, build-free review page."""
    return FileResponse(WEB_ROOT / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/profiles", response_model=list[FileOption])
def profiles() -> list[FileOption]:
    """List profile.json files available to the local picker."""
    return _file_options(PROFILE_ROOT, ("profile.json",))


@app.get("/programs", response_model=list[FileOption])
def programs() -> list[FileOption]:
    """List YAML program configurations available to the local picker."""
    return _file_options(PROGRAM_ROOT, ("*.yaml", "*.yml"))


@app.post("/review")
def review(request: ReviewRequest) -> Response:
    """Capture the original evidence before accepting student corrections."""
    profile_path = _selected_file(
        request.profile_path,
        root=PROFILE_ROOT,
        description="profile",
        allowed_names={"profile.json"},
    )
    program_path = _selected_file(
        request.program_path,
        root=PROGRAM_ROOT,
        description="program",
        allowed_suffixes={".yaml", ".yml"},
    )
    original = profile_path.read_bytes()
    if request.understanding is not None:
        try:
            profile_data = json.loads(original)
        except ValueError as error:
            raise HTTPException(422, "The source profile is not valid JSON.") from error
        response = _run_cli(
            ["unihive", "review-understanding", "--json"],
            json.dumps(
                {"profile": profile_data, "understanding": request.understanding}
            ).encode("utf-8"),
        )
    else:
        response = _run_cli(["unihive", "review", "--profile", "-", "--json"], original)
    if response.status_code != 200:
        return response
    draft = json.loads(response.body)
    review_id = _save_record(
        "drafts",
        {
            "draft": draft,
            "profile_path": str(profile_path),
            "program_path": str(program_path),
            "original_hash": sha256(original).hexdigest(),
        },
    )
    return JSONResponse(
        {"review_id": review_id, **draft}, headers={"Cache-Control": "no-store"}
    )


@app.post("/confirm")
def confirm(request: ConfirmRequest) -> Response:
    """Validate corrections through the CLI and save a separate immutable receipt."""
    if not request.confirmed:
        raise HTTPException(422, "Explicit evidence confirmation is required.")
    record = _read_record("drafts", request.review_id)
    original = _selected_file(
        record["profile_path"],
        root=PROFILE_ROOT,
        description="profile",
        allowed_names={"profile.json"},
    )
    if sha256(original.read_bytes()).hexdigest() != record["original_hash"]:
        raise HTTPException(
            409, "The source profile changed. Reload the evidence review."
        )
    draft = record["draft"]
    submission = {
        "profile": draft["profile"],
        "taxonomy_version": draft["taxonomy_version"],
        "confirmed": True,
        "corrections": request.corrections,
        "profile_details": request.profile_details,
        "additions": request.additions,
        "understanding": draft.get("understanding"),
        "claim_corrections": request.claim_corrections,
    }
    response = _run_cli(
        ["unihive", "confirm", "--json"], json.dumps(submission).encode("utf-8")
    )
    if response.status_code != 200:
        return response
    profile = json.loads(response.body)
    receipt = {
        "review_id": request.review_id,
        "program_path": record["program_path"],
        "confirmed_at": datetime.now(UTC).isoformat(),
        "submission": submission,
        "profile": profile,
        "original_hash": record["original_hash"],
        "parent_confirmation_id": record.get("parent_confirmation_id"),
        "followup_question": record.get("followup_question"),
        "understanding_sha256": (
            sha256(
                json.dumps(
                    draft["understanding"], sort_keys=True, ensure_ascii=False
                ).encode("utf-8")
            ).hexdigest()
            if draft.get("understanding") is not None
            else None
        ),
        "profile_sha256": sha256(
            json.dumps(profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
    }
    confirmation_id = _save_record("confirmations", receipt)
    return JSONResponse(
        {
            "confirmation_id": confirmation_id,
            "profile": profile,
            "confirmed_at": receipt["confirmed_at"],
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/receipt")
def receipt(request: ScoreRequest) -> Response:
    """Export the complete interpretation, submitted corrections and saved profile."""
    return JSONResponse(
        _read_record("confirmations", request.confirmation_id),
        headers={"Cache-Control": "no-store"},
    )


@app.post("/score")
def score(request: ScoreRequest) -> Response:
    """Score only a server-owned confirmed snapshot; return CLI stdout unchanged."""
    record = _read_record("confirmations", request.confirmation_id)
    program_path = _selected_file(
        record["program_path"],
        root=PROGRAM_ROOT,
        description="program",
        allowed_suffixes={".yaml", ".yml"},
    )
    command = [
        "unihive",
        "--score-only",
        "--profile",
        "-",
        "--program",
        str(program_path),
        "--json",
        "--report",
    ]
    return _run_cli(command, json.dumps(record["profile"]).encode("utf-8"))


@app.post("/questions")
def questions(request: ScoreRequest) -> Response:
    """Rank follow-ups from a freshly scored confirmed profile, through the CLI."""
    response = score(request)
    if response.status_code != 200:
        return response
    return _run_cli(["unihive", "questions", "--json"], bytes(response.body))


@app.post("/continue-review")
def continue_review(request: ContinueRequest) -> Response:
    """Start a new review from the latest confirmed profile, preserving lineage."""
    receipt = _read_record("confirmations", request.confirmation_id)
    parent = _read_record("drafts", receipt["review_id"])
    selected_question = None
    if request.question_id is not None:
        response = questions(ScoreRequest(confirmation_id=request.confirmation_id))
        if response.status_code != 200:
            return response
        selected_question = next(
            (
                item
                for item in json.loads(response.body)["questions"]
                if item["question"]["question_id"] == request.question_id
            ),
            None,
        )
        if selected_question is None:
            raise HTTPException(
                409, "This question is no longer current. Re-score to refresh."
            )
    response = _run_cli(
        ["unihive", "review", "--profile", "-", "--json"],
        json.dumps(receipt["profile"]).encode("utf-8"),
    )
    if response.status_code != 200:
        return response
    draft = json.loads(response.body)
    if receipt["submission"].get("understanding") is not None:
        draft["understanding"] = receipt["submission"]["understanding"]
        draft["claim_corrections"] = receipt["submission"]["claim_corrections"]
    identifier = _save_record(
        "drafts",
        {
            "draft": draft,
            "profile_path": parent["profile_path"],
            "program_path": receipt["program_path"],
            "original_hash": parent["original_hash"],
            "parent_confirmation_id": request.confirmation_id,
            "followup_question": selected_question,
        },
    )
    return JSONResponse(
        {"review_id": identifier, **draft, "followup_question": selected_question},
        headers={"Cache-Control": "no-store"},
    )


def _save_record(kind: str, record: dict) -> str:
    directory = PROJECT_ROOT / "data" / "reviews" / kind
    directory.mkdir(parents=True, exist_ok=True)
    identifier = uuid4().hex
    with (directory / f"{identifier}.json").open("x", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False)
    return identifier


def _read_record(kind: str, identifier: str) -> dict:
    # Also protect direct Python calls, independently of HTTP request validation.
    if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
        raise HTTPException(400, "Invalid review identifier.")
    try:
        return json.loads(
            (PROJECT_ROOT / "data" / "reviews" / kind / f"{identifier}.json").read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as error:
        raise HTTPException(404, "Review or confirmation was not found.") from error


def _run_cli(command: list[str], payload: bytes) -> Response:
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
            input=payload,
            timeout=30,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504,
            content={
                "error": {
                    "code": "CLI_TIMEOUT",
                    "message": "The UniHive command timed out.",
                }
            },
        )
    except OSError as error:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "CLI_UNAVAILABLE",
                    "message": "The UniHive CLI could not be started.",
                    "stderr": str(error),
                }
            },
        )

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "CLI_SCORE_FAILED",
                    "message": "The UniHive CLI could not process this request.",
                    "stderr": stderr or "No error details were provided.",
                    "return_code": completed.returncode,
                }
            },
        )

    return Response(
        content=completed.stdout,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def _file_options(root: Path, patterns: tuple[str, ...]) -> list[FileOption]:
    """Return deterministic, project-relative options under one data root."""
    if not root.is_dir():
        return []
    paths = {
        path.resolve()
        for pattern in patterns
        for path in root.rglob(pattern)
        if path.is_file()
    }
    return [
        FileOption(
            path=path.relative_to(PROJECT_ROOT).as_posix(),
            label=("Synthetic demo - " if root == DEMO_ROOT else "")
            + path.relative_to(root).as_posix(),
        )
        for path in sorted(paths)
    ]


def _selected_file(
    value: str,
    *,
    root: Path,
    description: str,
    allowed_names: set[str] | None = None,
    allowed_suffixes: set[str] | None = None,
) -> Path:
    """Resolve a picker value while keeping reads inside its catalog root."""
    supplied = Path(value)
    candidate = supplied if supplied.is_absolute() else PROJECT_ROOT / supplied
    resolved = candidate.resolve()
    allowed_root = root.resolve()
    if not resolved.is_relative_to(allowed_root):
        raise HTTPException(
            status_code=400,
            detail=f"The selected {description} is outside its data directory.",
        )
    if allowed_names is not None and resolved.name not in allowed_names:
        raise HTTPException(
            status_code=400,
            detail=f"The selected {description} has an unsupported file name.",
        )
    if allowed_suffixes is not None and resolved.suffix.lower() not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail=f"The selected {description} has an unsupported file type.",
        )
    if not resolved.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"The selected {description} file was not found.",
        )
    return resolved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use only the existing synthetic test fixtures",
    )
    args = parser.parse_args()
    if args.demo:
        PROFILE_ROOT = DEMO_ROOT
        PROGRAM_ROOT = DEMO_ROOT
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
