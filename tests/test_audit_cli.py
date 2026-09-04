"""Tests for replayable audits and the API-free deterministic CLI."""

from __future__ import annotations

import warnings
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import cli
from unihive.audit import (
    AuditReplayMismatch,
    AuditVersionError,
    create_audited_assessment,
    replay_assessment,
)
from unihive.eligibility import ProvisionalProgramWarning, load_program_config
from unihive.models import Assessment, StudentProfile
from unihive.scoring import (
    ProvisionalScoringWarning,
    load_scoring_configuration,
)
from unihive.taxonomy import ProvisionalTaxonomyWarning, load_taxonomy

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cli"
PROFILE_PATH = FIXTURE_DIR / "profile.json"
PROGRAM_PATH = FIXTURE_DIR / "program.yaml"
AS_OF = date(2026, 1, 1)
TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def audited_assessment() -> Assessment:
    profile = StudentProfile.model_validate_json(
        PROFILE_PATH.read_text(encoding="utf-8"), strict=True
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalTaxonomyWarning)
        warnings.simplefilter("ignore", ProvisionalProgramWarning)
        warnings.simplefilter("ignore", ProvisionalScoringWarning)
        taxonomy = load_taxonomy()
        program = load_program_config(PROGRAM_PATH)
        scoring = load_scoring_configuration()
    return create_audited_assessment(
        profile,
        program,
        taxonomy=taxonomy,
        scoring_configuration=scoring,
        as_of=AS_OF,
        timestamp=TIMESTAMP,
        engine_version="test-engine-v1",
    )


def test_audit_contains_replay_inputs_and_replays_byte_identically() -> None:
    expected = audited_assessment()

    replayed = replay_assessment(expected)

    assert expected.audit.profile_snapshot is not None
    assert expected.audit.program_config_snapshot is not None
    assert expected.audit.as_of == AS_OF
    assert expected.audit.scoring_config_version is not None
    assert replayed.model_dump_json() == expected.model_dump_json()


def test_replay_fails_if_output_was_changed() -> None:
    expected = audited_assessment()
    tampered = expected.model_copy(update={"pathway_readiness": None})

    with pytest.raises(AuditReplayMismatch, match="not byte-identical"):
        replay_assessment(tampered)


def test_replay_fails_on_version_drift() -> None:
    expected = audited_assessment()
    changed_audit = expected.audit.model_copy(
        update={"taxonomy_version": "changed-taxonomy"}
    )
    changed = expected.model_copy(update={"audit": changed_audit})

    with pytest.raises(AuditVersionError, match="taxonomy version"):
        replay_assessment(changed)


def test_score_only_cli_needs_no_api_key_and_emits_json_audit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = cli.main(
        [
            "--score-only",
            "--profile",
            str(PROFILE_PATH),
            "--program",
            str(PROGRAM_PATH),
            "--as-of",
            AS_OF.isoformat(),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assessment = Assessment.model_validate_json(captured.out, strict=True)

    assert result == 0
    assert assessment.audit.profile_snapshot is not None
    assert assessment.audit.program_config_snapshot is not None
    assert "Provisional configs in use:" in captured.err


def test_cli_replay_emits_the_same_assessment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.main(
        [
            "--score-only",
            "--profile",
            str(PROFILE_PATH),
            "--program",
            str(PROGRAM_PATH),
            "--as-of",
            AS_OF.isoformat(),
            "--json",
        ]
    )
    scored_output = capsys.readouterr().out
    audit_path = tmp_path / "assessment.json"
    audit_path.write_text(scored_output, encoding="utf-8")

    result = cli.main(["replay", "--audit", str(audit_path), "--json"])
    replay_output = capsys.readouterr().out

    assert result == 0
    expected = Assessment.model_validate_json(scored_output, strict=True)
    replayed = Assessment.model_validate_json(replay_output, strict=True)
    assert replayed.model_dump_json() == expected.model_dump_json()
