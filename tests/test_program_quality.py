"""Tests for program-data provenance gates and multi-program assessment."""

from __future__ import annotations

import json
import warnings
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import cli
from unihive.eligibility import ProvisionalProgramWarning, load_program_config
from unihive.models import ProgramConfig, StudentProfile
from unihive.program_quality import (
    LoadedProgramDataPolicy,
    ProgramDataIssueCode,
    ProgramDataPolicy,
    ProvisionalProgramDataPolicyWarning,
    assess_programs,
    load_program_data_policy,
    review_program_data,
)
from unihive.scoring import ProvisionalScoringWarning, load_scoring_configuration
from unihive.taxonomy import ProvisionalTaxonomyWarning, load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "cli"


def _program(**changes: object) -> ProgramConfig:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalProgramWarning)
        program = load_program_config(FIXTURES / "program.yaml")
    return program.model_copy(update=changes)


def _policy(**changes: object) -> LoadedProgramDataPolicy:
    values = ProgramDataPolicy(
        version="reviewed-policy-v1",
        maximum_age_days=365,
        provisional=False,
        validated_by="Program data reviewer",
        source="docs/engine_build_spec_v1.md",
    ).model_copy(update=changes)
    return LoadedProgramDataPolicy(version="reviewed-policy-v1:test", values=values)


def _profile() -> StudentProfile:
    return StudentProfile.model_validate_json(
        (FIXTURES / "profile.json").read_text(encoding="utf-8"), strict=True
    )


def test_checked_in_policy_warns_and_cannot_silently_enable_recommendations() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        policy = load_program_data_policy()

    review = review_program_data(
        _program(provisional=False, validated_by="Reviewer"),
        as_of=date(2026, 6, 1),
        policy=policy,
    )
    assert any(
        item.category is ProvisionalProgramDataPolicyWarning for item in captured
    )
    assert review.recommendation_ready is False
    assert review.issues[:2] == [
        ProgramDataIssueCode.POLICY_PROVISIONAL,
        ProgramDataIssueCode.POLICY_UNVALIDATED,
    ]


def test_program_must_be_current_nonprovisional_and_reviewed() -> None:
    review = review_program_data(
        _program(),
        as_of=date(2026, 6, 1),
        policy=_policy(),
    )
    assert review.recommendation_ready is False
    assert review.issues == [
        ProgramDataIssueCode.PROGRAM_PROVISIONAL,
        ProgramDataIssueCode.PROGRAM_UNVALIDATED,
    ]


def test_stale_and_future_verification_dates_are_explicit() -> None:
    stale = review_program_data(
        _program(
            provisional=False,
            validated_by="Reviewer",
            verified_on=date(2025, 1, 1),
        ),
        as_of=date(2026, 6, 1),
        policy=_policy(),
    )
    future = review_program_data(
        _program(
            provisional=False,
            validated_by="Reviewer",
            verified_on=date(2026, 7, 1),
        ),
        as_of=date(2026, 6, 1),
        policy=_policy(),
    )
    assert stale.issues == [ProgramDataIssueCode.SOURCE_STALE]
    assert future.issues == [ProgramDataIssueCode.VERIFIED_IN_FUTURE]


def test_ready_program_gets_complete_replayable_assessment() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalTaxonomyWarning)
        warnings.simplefilter("ignore", ProvisionalScoringWarning)
        taxonomy = load_taxonomy()
        scoring = load_scoring_configuration()
    program = _program(
        provisional=False,
        validated_by="Reviewer",
        verified_on=date(2026, 1, 1),
    )
    run = assess_programs(
        _profile(),
        [program],
        taxonomy=taxonomy,
        scoring_configuration=scoring,
        policy=_policy(),
        as_of=date(2026, 6, 1),
        timestamp=datetime(2026, 6, 1, tzinfo=UTC),
        engine_version="test-engine-v1",
    )
    result = run.results[0]
    assert result.review.recommendation_ready is True
    assert result.diagnostic_only is False
    assert result.assessment is not None
    assert result.assessment.audit.profile_snapshot == _profile()
    assert result.assessment.audit.program_config_snapshot == program
    assert result.assessment.audit.as_of == date(2026, 6, 1)


def test_blocked_program_is_unscored_unless_diagnostics_are_explicit() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalTaxonomyWarning)
        warnings.simplefilter("ignore", ProvisionalScoringWarning)
        taxonomy = load_taxonomy()
        scoring = load_scoring_configuration()
    common = {
        "taxonomy": taxonomy,
        "scoring_configuration": scoring,
        "policy": _policy(),
        "as_of": date(2026, 6, 1),
        "timestamp": datetime(2026, 6, 1, tzinfo=UTC),
        "engine_version": "test-engine-v1",
    }
    blocked = assess_programs(_profile(), [_program()], **common)
    diagnostic = assess_programs(
        _profile(),
        [_program()],
        include_blocked_diagnostics=True,
        **common,
    )
    assert blocked.results[0].assessment is None
    assert blocked.results[0].diagnostic_only is False
    assert diagnostic.results[0].assessment is not None
    assert diagnostic.results[0].diagnostic_only is True
    assert diagnostic.results[0].review.recommendation_ready is False


def test_recommend_cli_holds_provisional_records(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    program_dir = tmp_path / "programs"
    program_dir.mkdir()
    (program_dir / "example.yaml").write_text(
        (FIXTURES / "program.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = cli.main(
        [
            "recommend",
            "--profile",
            str(FIXTURES / "profile.json"),
            "--program-dir",
            str(program_dir),
            "--as-of",
            "2026-06-01",
        ]
    )
    assert result == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["results"][0]["review"]["recommendation_ready"] is False
    assert payload["results"][0]["assessment"] is None
