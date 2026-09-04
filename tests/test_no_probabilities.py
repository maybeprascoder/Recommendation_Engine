"""Serialized assessments must never expose admission-probability language."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import TypeAlias

from hypothesis import given
from hypothesis import strategies as st

from unihive.models import (
    CompetencyDemand,
    CompetencyLevel,
    EligibilityStatus,
    EvidenceState,
    ProgramConfig,
    StudentCompetency,
)
from unihive.scoring import (
    ProvisionalScoringWarning,
    load_scoring_configuration,
    score,
)

JsonTree: TypeAlias = (
    dict[str, "JsonTree"] | list["JsonTree"] | str | int | float | bool | None
)
AS_OF = date(2026, 1, 1)
TIMESTAMP = datetime(2026, 1, 1)
SOURCE_URL = "https://example.edu/program"
BANNED_TEXT = ("%", "chance", "probability", "odds", "likelihood")
PROBABILITY_FIELD_MARKERS = (
    "chance",
    "probability",
    "odds",
    "likelihood",
    "percent",
    "percentage",
)

with warnings.catch_warnings():
    warnings.simplefilter("ignore", ProvisionalScoringWarning)
    SCORING_CONFIGURATION = load_scoring_configuration()


@st.composite
def assessment_inputs(
    draw: st.DrawFn,
) -> tuple[list[StudentCompetency], ProgramConfig, EligibilityStatus]:
    """Generate a range of serializable scoring inputs."""
    state = draw(st.sampled_from(list(EvidenceState)))
    level = (
        draw(st.sampled_from(list(CompetencyLevel)))
        if state
        in {EvidenceState.VERIFIED_PRESENT, EvidenceState.SELF_REPORTED_PRESENT}
        else None
    )
    competency = StudentCompetency(
        competency_id="machine_learning",
        level=level,
        state=state,
        contributing_evidence_ids=[] if state is EvidenceState.UNKNOWN else ["e-1"],
        explanation_trace=[],
    )
    program = ProgramConfig(
        program_id="generated-program",
        university="Example University",
        degree="MS",
        demand_profile={
            "machine_learning": CompetencyDemand(
                required_level=draw(st.sampled_from(list(CompetencyLevel))),
                weight=Decimal(draw(st.integers(min_value=1, max_value=10)))
                / Decimal("10"),
            )
        },
        eligibility_rules=[],
        dimension_emphasis={},
        version="test-v1",
        source_url=SOURCE_URL,
        verified_on=AS_OF,
        provisional=True,
        validated_by=None,
    )
    eligibility = draw(st.sampled_from(list(EligibilityStatus)))
    return [competency], program, eligibility


def _walk_fields(value: JsonTree) -> Iterator[tuple[str, JsonTree]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk_fields(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_fields(child)


@given(assessment_inputs())
def test_serialized_assessments_contain_no_probabilities(
    inputs: tuple[list[StudentCompetency], ProgramConfig, EligibilityStatus],
) -> None:
    competencies, program, eligibility = inputs
    assessment = score(
        competencies,
        program,
        taxonomy_version="test-taxonomy-v1",
        engine_version="test-engine-v1",
        timestamp=TIMESTAMP,
        eligibility=eligibility,
        configuration=SCORING_CONFIGURATION,
    )
    serialized = assessment.model_dump_json().casefold()
    document: JsonTree = assessment.model_dump(mode="json")

    assert not any(term in serialized for term in BANNED_TEXT)
    for key, value in _walk_fields(document):
        if isinstance(value, float):
            assert not any(
                marker in key.casefold() for marker in PROBABILITY_FIELD_MARKERS
            )
