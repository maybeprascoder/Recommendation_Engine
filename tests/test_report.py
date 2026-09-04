"""Tests for pure-data report assembly and deterministic action simulation."""

from __future__ import annotations

import warnings
from datetime import date, datetime
from decimal import Decimal

from unihive.alternatives import AlternativePathwayResult, ChosenPath
from unihive.competency import resolve_competencies
from unihive.models import (
    Assessment,
    CompetencyDemand,
    CompetencyLevel,
    Confidence,
    Evidence,
    EvidenceState,
    ProgramConfig,
    ReadinessBand,
    StudentCompetency,
    StudentProfile,
)
from unihive.report import (
    ActionCandidate,
    ActionEffort,
    GapKind,
    ReportStructure,
    assemble_report,
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


def _taxonomy() -> Taxonomy:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalTaxonomyWarning)
        return load_taxonomy()


def _scoring_configuration() -> LoadedScoringConfiguration:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalScoringWarning)
        return load_scoring_configuration()


TAXONOMY = _taxonomy()
SCORING_CONFIGURATION = _scoring_configuration()


def profile_with(evidence: list[Evidence]) -> StudentProfile:
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
        evidence=evidence,
    )


def program(demands: dict[str, CompetencyDemand]) -> ProgramConfig:
    return ProgramConfig(
        program_id="test-program",
        university="Example University",
        degree="MS",
        demand_profile=demands,
        eligibility_rules=[],
        dimension_emphasis={},
        version="test-v1",
        source_url=SOURCE_URL,
        verified_on=AS_OF,
        provisional=True,
        validated_by=None,
    )


def pathways(current: Assessment) -> AlternativePathwayResult:
    return AlternativePathwayResult(
        chosen_path=ChosenPath(
            path_id="chosen-ms",
            field="Chosen MS",
            readiness_band=current.pathway_readiness,
        ),
        alternatives=[],
        suppressed=[],
    )


def test_report_has_six_sections_and_unknowns_are_never_gaps() -> None:
    profile = profile_with(
        [
            Evidence(
                id="programming-e",
                kind="project",
                raw_text="Built a substantial application",
                state=EvidenceState.VERIFIED_PRESENT,
                quality="substantial",
                depth="builder",
                recency=None,
                source="portfolio",
                extraction_confidence=Confidence.HIGH,
            )
        ]
    )
    target = program(
        {
            "programming": CompetencyDemand(
                required_level=CompetencyLevel.PROFICIENT,
                weight=Decimal("0.4"),
            ),
            "security": CompetencyDemand(
                required_level=CompetencyLevel.PROFICIENT,
                weight=Decimal("0.4"),
            ),
            "networking": CompetencyDemand(
                required_level=CompetencyLevel.PROFICIENT,
                weight=Decimal("0.2"),
            ),
        }
    )
    current = score(
        [
            StudentCompetency(
                competency_id="programming",
                level=CompetencyLevel.EXPERT,
                state=EvidenceState.VERIFIED_PRESENT,
                contributing_evidence_ids=["programming-e"],
                explanation_trace=[],
            ),
            StudentCompetency(
                competency_id="security",
                level=None,
                state=EvidenceState.CONFIRMED_ABSENT,
                contributing_evidence_ids=["security-answer"],
                explanation_trace=[],
            ),
            StudentCompetency(
                competency_id="networking",
                level=None,
                state=EvidenceState.UNKNOWN,
                contributing_evidence_ids=[],
                explanation_trace=[],
            ),
        ],
        target,
        taxonomy_version=TAXONOMY.version,
        engine_version="test-engine-v1",
        timestamp=TIMESTAMP,
        configuration=SCORING_CONFIGURATION,
    )

    report = assemble_report(
        profile,
        current,
        pathways(current),
        [],
        taxonomy=TAXONOMY,
        program=target,
        as_of=AS_OF,
        scoring_configuration=SCORING_CONFIGURATION,
    )

    assert len(ReportStructure.model_fields) == 6
    assert [item.competency_id for item in report.strengths] == ["programming"]
    assert [item.competency_id for item in report.gaps] == ["security"]
    assert report.gaps[0].kind is GapKind.CONFIRMED_ABSENT
    assert all(item.state is not EvidenceState.UNKNOWN for item in report.gaps)
    assert [item.field for item in report.what_we_cannot_assess_yet] == [
        "networking"
    ]


def publication(
    evidence_id: str,
    quality: str,
    depth: str,
) -> Evidence:
    return Evidence(
        id=evidence_id,
        kind="machine_learning_publication",
        raw_text=f"Hypothetical {quality} publication",
        state=EvidenceState.VERIFIED_PRESENT,
        quality=quality,
        depth=depth,
        recency=date(2025, 12, 1),
        source="hypothetical action",
        extraction_confidence=Confidence.HIGH,
    )


def _action_report() -> ReportStructure:
    profile = profile_with([publication("baseline", "preprint", "first_author")])
    target = program(
        {
            "machine_learning": CompetencyDemand(
                required_level=CompetencyLevel.EXPERT,
                weight=Decimal("1"),
            )
        }
    )
    competencies = resolve_competencies(profile, TAXONOMY, as_of=AS_OF)
    current = score(
        competencies,
        target,
        taxonomy_version=TAXONOMY.version,
        engine_version="test-engine-v1",
        timestamp=TIMESTAMP,
        configuration=SCORING_CONFIGURATION,
    )
    actions = [
        ActionCandidate(
            action_id="top-paper",
            title="Add top-tier first-author publication evidence",
            effort=ActionEffort.HIGH,
            hypothetical_evidence=publication(
                "top-paper-e", "top_tier_venue", "first_author"
            ),
        ),
        ActionCandidate(
            action_id="mid-paper",
            title="Add mid-tier first-author publication evidence",
            effort=ActionEffort.LOW,
            hypothetical_evidence=publication(
                "mid-paper-e", "mid_tier_conference", "first_author"
            ),
        ),
        ActionCandidate(
            action_id="workshop-paper",
            title="Add workshop publication evidence",
            effort=ActionEffort.MEDIUM,
            hypothetical_evidence=publication(
                "workshop-paper-e", "workshop", "first_author"
            ),
        ),
        ActionCandidate(
            action_id="another-preprint",
            title="Add another preprint",
            effort=ActionEffort.LOW,
            hypothetical_evidence=publication(
                "another-preprint-e", "preprint", "contributor"
            ),
        ),
    ]
    return assemble_report(
        profile,
        current,
        pathways(current),
        actions,
        taxonomy=TAXONOMY,
        program=target,
        as_of=AS_OF,
        scoring_configuration=SCORING_CONFIGURATION,
    )


def test_top_three_actions_are_ranked_by_simulated_impact_per_effort() -> None:
    report = _action_report()

    assert [action.action_id for action in report.top_actions] == [
        "mid-paper",
        "top-paper",
        "workshop-paper",
    ]
    assert [action.projected_band for action in report.top_actions] == [
        ReadinessBand.COMPETITIVE,
        ReadinessBand.STRONG,
        ReadinessBand.DEVELOPING,
    ]
    assert all(
        action.changed_competencies == ["machine_learning"]
        for action in report.top_actions
    )
    assert all("deterministic rescoring" in action.why for action in report.top_actions)


def test_report_action_simulation_is_deterministic() -> None:
    outputs = {_action_report().model_dump_json() for _ in range(20)}
    assert len(outputs) == 1
