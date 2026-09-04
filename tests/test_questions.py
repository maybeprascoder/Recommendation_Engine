"""Tests for deterministic, demand-weighted next-best-question ranking."""

from __future__ import annotations

import warnings
from datetime import date, datetime
from decimal import Decimal

from unihive.models import (
    Assessment,
    CompetencyDemand,
    CompetencyLevel,
    EvidenceState,
    ProgramConfig,
    StudentCompetency,
)
from unihive.questions import (
    LoadedQuestionBank,
    ProvisionalQuestionBankWarning,
    QuestionResolutionType,
    load_question_bank,
    next_best_question,
    rank_questions,
)
from unihive.scoring import (
    LoadedScoringConfiguration,
    ProvisionalScoringWarning,
    load_scoring_configuration,
    score,
)

AS_OF = date(2026, 1, 1)
TIMESTAMP = datetime(2026, 1, 1)
SOURCE_URL = "https://example.edu/program"


def _question_bank() -> LoadedQuestionBank:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalQuestionBankWarning)
        return load_question_bank()


def _scoring_configuration() -> LoadedScoringConfiguration:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalScoringWarning)
        return load_scoring_configuration()


QUESTION_BANK = _question_bank()
SCORING_CONFIGURATION = _scoring_configuration()


def competency(
    competency_id: str,
    state: EvidenceState = EvidenceState.UNKNOWN,
) -> StudentCompetency:
    """Build a resolved competency state for question-ranking tests."""
    is_present = state in {
        EvidenceState.VERIFIED_PRESENT,
        EvidenceState.SELF_REPORTED_PRESENT,
    }
    return StudentCompetency(
        competency_id=competency_id,
        level=CompetencyLevel.PROFICIENT if is_present else None,
        state=state,
        contributing_evidence_ids=[f"{competency_id}-e"] if is_present else [],
        explanation_trace=[],
    )


def assessment(
    *,
    networking: EvidenceState = EvidenceState.UNKNOWN,
    operating_systems: EvidenceState = EvidenceState.UNKNOWN,
    security: EvidenceState = EvidenceState.UNKNOWN,
) -> Assessment:
    """Score a fixture with deliberately different competency demands."""
    program = ProgramConfig(
        program_id="cybersecurity-ms",
        university="Example University",
        degree="MS",
        demand_profile={
            "networking": CompetencyDemand(
                required_level=CompetencyLevel.PROFICIENT,
                weight=Decimal("0.9"),
            ),
            "operating_systems": CompetencyDemand(
                required_level=CompetencyLevel.PROFICIENT,
                weight=Decimal("0.4"),
            ),
            "security": CompetencyDemand(
                required_level=CompetencyLevel.PROFICIENT,
                weight=Decimal("0.7"),
            ),
        },
        eligibility_rules=[],
        dimension_emphasis={},
        version="test-v1",
        source_url=SOURCE_URL,
        verified_on=AS_OF,
        provisional=True,
        validated_by=None,
    )
    return score(
        [
            competency("networking", networking),
            competency("operating_systems", operating_systems),
            competency("security", security),
        ],
        program,
        taxonomy_version="test-taxonomy-v1",
        engine_version="test-engine-v1",
        timestamp=TIMESTAMP,
        configuration=SCORING_CONFIGURATION,
    )


def test_unknown_competencies_are_ranked_by_program_demand() -> None:
    ranked = rank_questions(assessment(), question_bank=QUESTION_BANK)

    assert [question.resolves_id for question in ranked] == [
        "networking",
        "security",
        "operating_systems",
    ]
    assert ranked[0].demand_weight == Decimal("0.9")
    assert ranked[0].expected_effect == (
        "This would resolve networking, currently unknown with demand weight "
        "0.9 for your target."
    )


def test_resolved_competency_is_not_asked_again() -> None:
    ranked = rank_questions(
        assessment(networking=EvidenceState.VERIFIED_PRESENT),
        question_bank=QUESTION_BANK,
    )

    assert "networking" not in {question.resolves_id for question in ranked}


def test_missing_field_questions_follow_demand_weighted_questions() -> None:
    current = assessment(
        networking=EvidenceState.VERIFIED_PRESENT,
        operating_systems=EvidenceState.VERIFIED_PRESENT,
        security=EvidenceState.VERIFIED_PRESENT,
    )
    updated_audit = current.audit.model_copy(
        update={"missing_fields": ["goals", "constraints"]}
    )
    current = current.model_copy(update={"audit": updated_audit})

    ranked = rank_questions(current, question_bank=QUESTION_BANK)

    assert [question.resolves_type for question in ranked] == [
        QuestionResolutionType.FIELD,
        QuestionResolutionType.FIELD,
    ]
    assert [question.resolves_id for question in ranked] == [
        "goals",
        "constraints",
    ]
    assert all(question.demand_weight is None for question in ranked)


def test_next_best_question_returns_highest_demand_unknown() -> None:
    question = next_best_question(assessment(), question_bank=QUESTION_BANK)

    assert question is not None
    assert question.resolves_id == "networking"


def test_question_ranking_is_deterministic_across_100_runs() -> None:
    current = assessment()
    serialized = {
        tuple(
            question.model_dump_json()
            for question in rank_questions(current, question_bank=QUESTION_BANK)
        )
        for _ in range(100)
    }

    assert len(serialized) == 1
