"""Property tests for the UniHive engine's non-negotiable invariants."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from unihive.competency import resolve_competencies
from unihive.models import (
    Assessment,
    CompetencyDemand,
    CompetencyLevel,
    Confidence,
    EligibilityStatus,
    Evidence,
    EvidenceState,
    ProgramConfig,
    StudentCompetency,
    StudentProfile,
)
from unihive.scoring import (
    LoadedScoringConfiguration,
    ProvisionalScoringWarning,
    load_scoring_configuration,
    score,
)
from unihive.taxonomy import (
    ProvisionalTaxonomyWarning,
    Taxonomy,
    load_taxonomy,
)

AS_OF = date(2026, 1, 1)
TIMESTAMP = datetime(2026, 1, 1)
SOURCE_URL = "https://example.edu/program"
COMPETENCY_IDS = ("machine_learning", "programming", "statistics")
READ_FIELDS = {
    "pathway_readiness",
    "program_alignment",
    "eligibility",
    "preference_fit",
    "admissions_outlook",
    "data_confidence",
}
FORBIDDEN_AGGREGATES = {"overall_score", "total", "final_score", "aggregate"}
CONFIDENCE_ORDER = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
}


@dataclass(frozen=True)
class ProfileProgramCase:
    """A generated competency profile paired with one program demand profile."""

    competencies: list[StudentCompetency]
    program: ProgramConfig


def _weight() -> st.SearchStrategy[Decimal]:
    return st.integers(min_value=1, max_value=10).map(
        lambda value: Decimal(value) / Decimal("10")
    )


def _level() -> st.SearchStrategy[CompetencyLevel]:
    return st.sampled_from(list(CompetencyLevel))


def _known_competency(
    competency_id: str,
    state: EvidenceState,
    level: CompetencyLevel | None,
) -> StudentCompetency:
    evidence_ids = [] if state is EvidenceState.UNKNOWN else [f"{competency_id}-e"]
    return StudentCompetency(
        competency_id=competency_id,
        level=level,
        state=state,
        contributing_evidence_ids=evidence_ids,
        explanation_trace=[],
    )


def _program(
    demand_profile: dict[str, CompetencyDemand],
    *,
    program_id: str = "generated-program",
) -> ProgramConfig:
    return ProgramConfig(
        program_id=program_id,
        university="Example University",
        degree="MS",
        demand_profile=demand_profile,
        eligibility_rules=[],
        dimension_emphasis={},
        version="test-v1",
        source_url=SOURCE_URL,
        verified_on=AS_OF,
        provisional=True,
        validated_by=None,
    )


@st.composite
def profile_program_cases(draw: st.DrawFn) -> ProfileProgramCase:
    """Generate complete profiles and demand profiles before testing properties."""
    demands: dict[str, CompetencyDemand] = {}
    competencies: list[StudentCompetency] = []
    for competency_id in COMPETENCY_IDS:
        required_level = draw(_level())
        demands[competency_id] = CompetencyDemand(
            required_level=required_level,
            weight=draw(_weight()),
        )
        state = draw(st.sampled_from(list(EvidenceState)))
        level = draw(_level()) if state in _present_states() else None
        competencies.append(_known_competency(competency_id, state, level))
    return ProfileProgramCase(competencies, _program(demands))


@st.composite
def unknown_flip_cases(draw: st.DrawFn) -> ProfileProgramCase:
    """Generate a known baseline plus one demanded, not-yet-assessed competency."""
    baseline_id, target_id = COMPETENCY_IDS[:2]
    target_required = draw(_level())
    demands = {
        baseline_id: CompetencyDemand(
            required_level=draw(_level()), weight=draw(_weight())
        ),
        target_id: CompetencyDemand(
            required_level=target_required, weight=draw(_weight())
        ),
    }
    competencies = [
        _known_competency(
            baseline_id,
            draw(st.sampled_from(tuple(_present_states()))),
            draw(_level()),
        ),
        _known_competency(target_id, EvidenceState.UNKNOWN, target_required),
    ]
    return ProfileProgramCase(competencies, _program(demands))


def _scoring_configuration() -> LoadedScoringConfiguration:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalScoringWarning)
        return load_scoring_configuration()


def _taxonomy() -> Taxonomy:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalTaxonomyWarning)
        return load_taxonomy()


SCORING_CONFIGURATION = _scoring_configuration()
TAXONOMY = _taxonomy()


def _score(
    case: ProfileProgramCase,
    *,
    eligibility: EligibilityStatus = EligibilityStatus.UNKNOWN,
) -> Assessment:
    return score(
        case.competencies,
        case.program,
        taxonomy_version="test-taxonomy-v1",
        engine_version="test-engine-v1",
        timestamp=TIMESTAMP,
        eligibility=eligibility,
        configuration=SCORING_CONFIGURATION,
    )


def _readiness(assessment: Assessment) -> Decimal:
    readiness = assessment.program_alignment.readiness_value
    assert readiness is not None
    return readiness


def _replace_target(
    case: ProfileProgramCase,
    *,
    state: EvidenceState,
) -> ProfileProgramCase:
    target = case.competencies[1]
    replacement = target.model_copy(
        update={
            "state": state,
            "level": None if state is EvidenceState.CONFIRMED_ABSENT else target.level,
            "contributing_evidence_ids": [f"{target.competency_id}-e"],
        }
    )
    return ProfileProgramCase(
        [case.competencies[0], replacement],
        case.program,
    )


@given(unknown_flip_cases())
def test_unknown_to_confirmed_absent_never_increases_readiness(
    case: ProfileProgramCase,
) -> None:
    unknown = _score(case)
    absent = _score(_replace_target(case, state=EvidenceState.CONFIRMED_ABSENT))

    assert _readiness(absent) <= _readiness(unknown)
    assert case.competencies[1].competency_id in unknown.not_assessed
    assert case.competencies[1].competency_id not in absent.not_assessed


@given(unknown_flip_cases())
def test_unknown_to_verified_at_demonstrated_requirement_is_monotonic(
    case: ProfileProgramCase,
) -> None:
    """Revealing evidence at its demonstrated requirement cannot hurt either read."""
    unknown = _score(case)
    verified = _score(_replace_target(case, state=EvidenceState.VERIFIED_PRESENT))

    assert _readiness(verified) >= _readiness(unknown)
    assert (
        CONFIDENCE_ORDER[verified.data_confidence]
        >= CONFIDENCE_ORDER[unknown.data_confidence]
    )


def _profile_with_publication(quality: str) -> StudentProfile:
    evidence = Evidence(
        id="ml-paper",
        kind="machine_learning_publication",
        raw_text="Structured publication evidence",
        state=EvidenceState.VERIFIED_PRESENT,
        quality=quality,
        depth="first_author",
        recency=date(2025, 12, 1),
        source="test fixture",
        extraction_confidence=Confidence.HIGH,
    )
    return StudentProfile(
        academic_history=[],
        normalized_gpa=None,
        courses=[],
        skills=[],
        projects=[],
        research=[],
        work=[],
        goals=[],
        constraints=[],
        tests=[],
        evidence=[evidence],
    )


QUALITY_LADDER = (
    "preprint",
    "workshop",
    "mid_tier_conference",
    "top_tier_venue",
)


@given(st.integers(min_value=0, max_value=len(QUALITY_LADDER) - 2), _level())
def test_upgrading_evidence_quality_never_lowers_readiness(
    quality_index: int,
    required_level: CompetencyLevel,
) -> None:
    program = _program(
        {
            "machine_learning": CompetencyDemand(
                required_level=required_level,
                weight=Decimal("1"),
            )
        }
    )
    lower = resolve_competencies(
        _profile_with_publication(QUALITY_LADDER[quality_index]),
        TAXONOMY,
        as_of=AS_OF,
    )
    higher = resolve_competencies(
        _profile_with_publication(QUALITY_LADDER[quality_index + 1]),
        TAXONOMY,
        as_of=AS_OF,
    )

    lower_assessment = _score(ProfileProgramCase(lower, program))
    higher_assessment = _score(ProfileProgramCase(higher, program))

    assert _readiness(higher_assessment) >= _readiness(lower_assessment)


@settings(deadline=None)  # Correctness over 100 replays, not a wall-clock benchmark.
@given(profile_program_cases())
def test_scoring_is_byte_deterministic_across_100_runs(
    case: ProfileProgramCase,
) -> None:
    outputs = {_score(case).model_dump_json() for _ in range(100)}
    assert len(outputs) == 1


def test_program_relativity_inverts_student_ordering() -> None:
    """The Experience doc's research/project profiles invert by program shape."""
    student_a = [
        _known_competency("research", EvidenceState.UNKNOWN, None),
        _known_competency(
            "projects", EvidenceState.VERIFIED_PRESENT, CompetencyLevel.ADVANCED
        ),
    ]
    student_b = [
        _known_competency(
            "research", EvidenceState.VERIFIED_PRESENT, CompetencyLevel.EXPERT
        ),
        _known_competency(
            "projects", EvidenceState.VERIFIED_PRESENT, CompetencyLevel.INTRODUCTORY
        ),
    ]
    research_program = _program(
        {
            "research": CompetencyDemand(
                required_level=CompetencyLevel.EXPERT, weight=Decimal("0.9")
            ),
            "projects": CompetencyDemand(
                required_level=CompetencyLevel.EXPERT, weight=Decimal("0.1")
            ),
        },
        program_id="research-ms",
    )
    professional_program = _program(
        {
            "research": CompetencyDemand(
                required_level=CompetencyLevel.EXPERT, weight=Decimal("0.1")
            ),
            "projects": CompetencyDemand(
                required_level=CompetencyLevel.EXPERT, weight=Decimal("0.9")
            ),
        },
        program_id="professional-ms",
    )

    a_research = _score(ProfileProgramCase(student_a, research_program))
    b_research = _score(ProfileProgramCase(student_b, research_program))
    a_professional = _score(ProfileProgramCase(student_a, professional_program))
    b_professional = _score(ProfileProgramCase(student_b, professional_program))

    assert _readiness(b_research) > _readiness(a_research)
    assert _readiness(a_professional) > _readiness(b_professional)


@given(profile_program_cases(), st.sampled_from(list(EligibilityStatus)))
def test_six_reads_stay_separate_and_eligibility_does_not_change_readiness(
    case: ProfileProgramCase,
    eligibility: EligibilityStatus,
) -> None:
    baseline = _score(case)
    changed_eligibility = _score(case, eligibility=eligibility)

    assert set(Assessment.model_fields) == READ_FIELDS | {"audit", "not_assessed"}
    assert not FORBIDDEN_AGGREGATES & Assessment.model_fields.keys()
    assert changed_eligibility.program_alignment == baseline.program_alignment
    assert changed_eligibility.pathway_readiness == baseline.pathway_readiness


def _present_states() -> set[EvidenceState]:
    return {
        EvidenceState.VERIFIED_PRESENT,
        EvidenceState.SELF_REPORTED_PRESENT,
    }
