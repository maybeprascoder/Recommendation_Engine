"""Complete profile updates and progressive uncertainty use confirmed inputs."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from unihive.audit import create_audited_assessment, replay_assessment
from unihive.eligibility import load_program_config
from unihive.followup import build_followup_questions
from unihive.models import EvidenceState, StudentProfile
from unihive.questions import load_question_bank
from unihive.response import ScoringResponse, build_scoring_response
from unihive.review import ConfirmationRequest, confirm_evidence
from unihive.scoring import load_scoring_configuration
from unihive.taxonomy import load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures/cli"


def payload() -> dict:
    profile = json.loads((FIXTURES / "profile.json").read_text())
    return {
        "profile": profile,
        "taxonomy_version": load_taxonomy().version,
        "confirmed": True,
        "corrections": [
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
            for item in profile["evidence"]
        ],
    }


def confirm(data: dict) -> StudentProfile:
    return confirm_evidence(
        ConfirmationRequest.model_validate_json(json.dumps(data), strict=True),
        load_taxonomy(),
    )


def response(profile: StudentProfile) -> ScoringResponse:
    taxonomy = load_taxonomy()
    scoring = load_scoring_configuration()
    assessment = create_audited_assessment(
        profile,
        load_program_config(FIXTURES / "program.yaml"),
        taxonomy=taxonomy,
        scoring_configuration=scoring,
        as_of=date(2026, 1, 1),
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        engine_version="test",
    )
    return build_scoring_response(
        assessment, taxonomy=taxonomy, scoring_configuration=scoring
    )


def test_all_profile_sections_edit_without_overwriting_evidence() -> None:
    data = payload()
    details = {
        key: value for key, value in data["profile"].items() if key != "evidence"
    }
    details.update(
        academic_history=[{"degree": "BS", "completed": False}],
        normalized_gpa="2.5",
        courses=[{"name": "networks", "completed": None}],
        skills=["Python"],
        projects=[{"name": "App", "details": {"team": ["A", "B"]}}],
        research=[{"name": "Study"}],
        work=[{"months": 0}],
        tests=[{"test": "GRE", "taken": False, "score": None}],
        goals=["Research"],
        constraints=["Part-time"],
        citizenship="Example",
        residency=None,
    )
    data["profile_details"] = details
    original = json.dumps(data["profile"], sort_keys=True)
    profile = confirm(data)
    assert profile.model_dump(mode="json", exclude={"evidence"}) == details
    assert json.dumps(data["profile"], sort_keys=True) == original
    assert profile.evidence[0].state == EvidenceState.VERIFIED_PRESENT
    scored = response(profile)
    assert scored.eligibility_result.status.value == "NOT_CURRENTLY_ELIGIBLE"
    assert replay_assessment(scored.assessment) == scored.assessment


@pytest.mark.parametrize(
    "bad",
    [
        {"evidence": []},
        {"normalized_gpa": "NaN"},
        {"normalized_gpa": "-1"},
        {"tests": "a test"},
    ],
)
def test_invalid_profile_details_fail_closed(bad: dict) -> None:
    data = payload()
    data["profile_details"] = {
        key: value for key, value in data["profile"].items() if key != "evidence"
    }
    data["profile_details"].update(citizenship=None, residency=None, **bad)
    with pytest.raises(ValueError):
        confirm(data)


def test_new_evidence_is_student_supplied_and_has_no_verification_upgrade() -> None:
    data = payload()
    new = {
        **data["corrections"][0],
        "evidence_id": "student-1",
        "raw_text": "My project",
        "kind": "project",
    }
    data["additions"] = [new]
    profile = confirm(data)
    added = profile.evidence[-1]
    assert added.state == EvidenceState.SELF_REPORTED_PRESENT
    assert added.source == "Student supplied: My project"
    assert added.extraction_confidence.value == "LOW"
    assert (
        response(profile).assessment.pathway_readiness
        == response(confirm(payload())).assessment.pathway_readiness
    )
    for identifier in ("ml-paper", "student-1"):
        data["additions"] = [new, {**new, "evidence_id": identifier}]
        with pytest.raises(ValueError, match="IDs"):
            confirm(data)


def test_followups_cover_missing_evidence_and_fields_then_disappear_when_answered() -> (
    None
):
    data = payload()
    data["profile"].update(goals=[], constraints=[], normalized_gpa=None)
    data["corrections"][0]["state"] = "UNKNOWN"
    scored = response(confirm(data))
    original = scored.model_dump_json()
    questions = build_followup_questions(scored, load_taxonomy(), load_question_bank())
    assert [item.question.resolves_id for item in questions.questions] == [
        "machine_learning",
        "goals",
        "constraints",
        "normalized_gpa",
    ]
    assert questions.questions[0].evidence_kinds == ["machine_learning_publication"]
    assert scored.model_dump_json() == original
    assert (
        build_followup_questions(scored, load_taxonomy(), load_question_bank())
        == questions
    )
    data["profile"].update(
        goals=["Research"], constraints=["No stated constraints"], normalized_gpa="3.7"
    )
    data["corrections"][0]["state"] = "SELF_REPORTED_PRESENT"
    answered = response(confirm(data))
    assert (
        build_followup_questions(
            answered, load_taxonomy(), load_question_bank()
        ).questions
        == []
    )


def test_unmapped_competency_questions_do_not_promise_resolution() -> None:
    scored = response(confirm(payload()))
    demand = scored.assessment.audit.program_config_snapshot
    assert demand is not None
    network_program = demand.model_copy(
        update={
            "demand_profile": {"networking": next(iter(demand.demand_profile.values()))}
        }
    )
    assessment = create_audited_assessment(
        confirm(payload()),
        network_program,
        taxonomy=load_taxonomy(),
        scoring_configuration=load_scoring_configuration(),
        as_of=date(2026, 1, 1),
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        engine_version="test",
    )
    result = build_followup_questions(
        build_scoring_response(
            assessment,
            taxonomy=load_taxonomy(),
            scoring_configuration=load_scoring_configuration(),
        ),
        load_taxonomy(),
        load_question_bank(),
    )
    assert result.questions[0].evidence_kinds == []
    assert "remain unassessed" in result.questions[0].guidance
