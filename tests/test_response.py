"""End-to-end deterministic report behavior using synthetic fixture data."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import cli
from unihive.audit import AuditReplayMismatch, create_audited_assessment
from unihive.eligibility import load_program_config
from unihive.models import EvidenceState, StudentProfile
from unihive.response import LimitationCode, ScoringResponse, build_scoring_response
from unihive.scoring import load_scoring_configuration
from unihive.taxonomy import load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "cli"
AS_OF = date(2026, 1, 1)


def response_for(profile: StudentProfile, *, no_rules: bool = False) -> ScoringResponse:
    taxonomy = load_taxonomy()
    config = load_scoring_configuration()
    program = load_program_config(FIXTURES / "program.yaml")
    if no_rules:
        program = program.model_copy(update={"eligibility_rules": []})
    assessment = create_audited_assessment(
        profile,
        program,
        taxonomy=taxonomy,
        scoring_configuration=config,
        as_of=AS_OF,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        engine_version="0.1.0",
    )
    before = assessment.model_dump_json()
    result = build_scoring_response(
        assessment,
        taxonomy=taxonomy,
        scoring_configuration=config,
    )
    assert result.assessment.model_dump_json() == before
    return result


def profile() -> StudentProfile:
    return StudentProfile.model_validate_json(
        (FIXTURES / "profile.json").read_text(encoding="utf-8"),
        strict=True,
    )


def test_report_contains_six_sections_provenance_and_explicit_limits() -> None:
    result = response_for(profile())
    report = result.report
    assert list(type(report).model_fields) == [
        "what_we_understand_about_you",
        "strengths",
        "gaps",
        "chosen_path_and_alternatives",
        "top_actions",
        "what_we_cannot_assess_yet",
    ]
    assert report.what_we_understand_about_you[0].evidence_id == "ml-paper"
    assert report.strengths[0].evidence_ids == ["ml-paper"]
    assert report.gaps == []
    assert (
        report.chosen_path_and_alternatives.chosen_path.field == "MS Machine Learning"
    )
    assert report.chosen_path_and_alternatives.chosen_path.path_id == "example-ml-ms"
    assert report.chosen_path_and_alternatives.alternatives == []
    assert report.top_actions == []
    assert {item.code for item in result.limitations} == set(LimitationCode)
    assert result.provisional is True
    rule = result.eligibility_result.rule_breakdown[0]
    assert rule.rule_id == "minimum-gpa"
    assert str(rule.source_url) == "https://example.edu/program/requirements"
    assert result.eligibility_result.status == result.assessment.eligibility
    serialized = result.model_dump_json().lower()
    assert not any(
        term in serialized
        for term in ("%", "probability", "chance", "odds", "likelihood")
    )


@pytest.mark.parametrize(
    "state", [EvidenceState.UNKNOWN, EvidenceState.CONFIRMED_ABSENT]
)
def test_unknown_and_absent_stay_distinct_in_complete_report(
    state: EvidenceState,
) -> None:
    original = profile()
    evidence = original.evidence[0].model_copy(update={"state": state, "quality": None})
    result = response_for(
        original.model_copy(update={"evidence": [evidence], "normalized_gpa": None})
    )
    unknowns = {item.field for item in result.report.what_we_cannot_assess_yet}
    assert "normalized_gpa" in unknowns
    assert "normalized_gpa" in result.eligibility_result.needed_information
    if state is EvidenceState.UNKNOWN:
        assert "machine_learning" in unknowns
        assert result.report.gaps == []
        assert result.assessment.pathway_readiness is None
    else:
        assert "machine_learning" not in unknowns
        assert result.report.gaps[0].state is EvidenceState.CONFIRMED_ABSENT


def test_known_low_level_evidence_is_a_gap_not_an_unknown() -> None:
    original = profile()
    evidence = original.evidence[0].model_copy(update={"quality": "preprint"})
    result = response_for(original.model_copy(update={"evidence": [evidence]}))
    assert result.report.gaps[0].kind.value == "BELOW_EXPECTED_LEVEL"
    assert result.report.gaps[0].evidence_ids == ["ml-paper"]
    assert result.report.what_we_cannot_assess_yet == []


def test_missing_eligibility_rules_are_named_in_report() -> None:
    result = response_for(profile(), no_rules=True)
    assert result.eligibility_result.status.value == "UNKNOWN"
    assert result.eligibility_result.rule_breakdown == []
    assert "program.eligibility_rules" in {
        item.field for item in result.report.what_we_cannot_assess_yet
    }


def test_report_cli_and_replay_preserve_complete_response(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    command = [
        "--score-only",
        "--profile",
        str(FIXTURES / "profile.json"),
        "--program",
        str(FIXTURES / "program.yaml"),
        "--as-of",
        "2026-01-01",
        "--json",
    ]
    assert cli.main(command) == 0
    baseline = capsys.readouterr().out
    assert cli.main([*command, "--report"]) == 0
    response = capsys.readouterr().out
    saved = ScoringResponse.model_validate_json(response, strict=True)
    assert saved.assessment.model_dump(mode="json") == json.loads(baseline)
    path = tmp_path / "response.json"
    path.write_text(response, encoding="utf-8")
    assert cli.main(["replay", "--audit", str(path), "--json", "--report"]) == 0
    assert capsys.readouterr().out == response
    # Legacy assessment JSON can also produce the same report during replay.
    path.write_text(baseline, encoding="utf-8")
    assert cli.main(["replay", "--audit", str(path), "--json", "--report"]) == 0
    assert capsys.readouterr().out == response
    altered = json.loads(response)
    altered["report"]["strengths"] = []
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(AuditReplayMismatch, match="report"):
        cli.main(["replay", "--audit", str(path), "--json", "--report"])


def test_report_requires_json() -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["--report"])
    assert error.value.code == 2
