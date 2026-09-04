"""Pure-data six-section report assembly and deterministic action simulation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final, Self

from pydantic import model_validator

from unihive.alternatives import AlternativePathwayResult
from unihive.competency import resolve_competencies
from unihive.models import (
    Assessment,
    CompetencyLevel,
    Confidence,
    CoreModel,
    Evidence,
    EvidenceState,
    ProgramConfig,
    ReadinessBand,
    StudentProfile,
)
from unihive.scoring import (
    LoadedScoringConfiguration,
    load_scoring_configuration,
    score,
)
from unihive.taxonomy import Taxonomy

MAX_REPORT_ACTIONS: Final = 3
_BAND_ORDER = tuple(ReadinessBand)


class ReportError(ValueError):
    """Raised when a report cannot be assembled from consistent frozen data."""


class ActionEffort(StrEnum):
    """Categorical effort estimate supplied with a candidate action."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class GapKind(StrEnum):
    """Known evidence states that can constitute a report gap."""

    CONFIRMED_ABSENT = "CONFIRMED_ABSENT"
    BELOW_EXPECTED_LEVEL = "BELOW_EXPECTED_LEVEL"


class UnderstoodEvidence(CoreModel):
    """One sourced profile fact rendered in the first report section."""

    evidence_id: str
    raw_text: str
    state: EvidenceState
    source: str | None
    extraction_confidence: Confidence


class ReportCompetency(CoreModel):
    """A known competency strength or confirmed gap."""

    competency_id: str
    state: EvidenceState
    demonstrated_level: CompetencyLevel | None
    expected_level: CompetencyLevel
    evidence_ids: list[str]


class ConfirmedGap(ReportCompetency):
    """A known shortfall that is never constructed from unknown evidence."""

    kind: GapKind


class ReportUnknown(CoreModel):
    """A named field or demanded competency that is not yet assessed."""

    field: str
    demand_weight: Decimal | None
    needed_to_resolve: str


class ActionCandidate(CoreModel):
    """A hypothetical evidence addition considered for the action plan."""

    action_id: str
    title: str
    effort: ActionEffort
    hypothetical_evidence: Evidence

    @model_validator(mode="after")
    def validate_hypothesis(self) -> Self:
        if self.hypothetical_evidence.state not in {
            EvidenceState.VERIFIED_PRESENT,
            EvidenceState.SELF_REPORTED_PRESENT,
        }:
            raise ValueError("hypothetical action evidence must be present")
        return self


class ReportAction(CoreModel):
    """A simulated action with its band movement and evidence-based reason."""

    action_id: str
    title: str
    effort: ActionEffort
    current_band: ReadinessBand | None
    projected_band: ReadinessBand | None
    changed_competencies: list[str]
    why: str


class ReportStructure(CoreModel):
    """The six report sections defined by Experience Doc section 3."""

    what_we_understand_about_you: list[UnderstoodEvidence]
    strengths: list[ReportCompetency]
    gaps: list[ConfirmedGap]
    chosen_path_and_alternatives: AlternativePathwayResult
    top_actions: list[ReportAction]
    what_we_cannot_assess_yet: list[ReportUnknown]


def assemble_report(
    profile: StudentProfile,
    assessment: Assessment,
    pathways: AlternativePathwayResult,
    action_candidates: Sequence[ActionCandidate],
    *,
    taxonomy: Taxonomy,
    program: ProgramConfig,
    as_of: date,
    scoring_configuration: LoadedScoringConfiguration | None = None,
) -> ReportStructure:
    """Implement Experience Doc §3 as six immutable, ordered data sections."""
    if pathways.chosen_path.readiness_band is not assessment.pathway_readiness:
        raise ReportError("chosen-path band differs from the frozen assessment")

    loaded_scoring = scoring_configuration or load_scoring_configuration()
    if (
        loaded_scoring.version
        != assessment.program_alignment.band_config_version
    ):
        raise ReportError("scoring configuration differs from the assessment")

    understood = [
        UnderstoodEvidence(
            evidence_id=evidence.id,
            raw_text=evidence.raw_text,
            state=evidence.state,
            source=evidence.source,
            extraction_confidence=evidence.extraction_confidence,
        )
        for evidence in profile.evidence
    ]
    strengths, gaps = _strengths_and_gaps(assessment)
    unknowns = _unknowns(assessment)
    actions = _simulate_actions(
        profile,
        assessment,
        action_candidates,
        taxonomy=taxonomy,
        program=program,
        as_of=as_of,
        scoring_configuration=loaded_scoring,
    )
    return ReportStructure(
        what_we_understand_about_you=understood,
        strengths=strengths,
        gaps=gaps,
        chosen_path_and_alternatives=pathways,
        top_actions=actions,
        what_we_cannot_assess_yet=unknowns,
    )


def build_report(
    profile: StudentProfile,
    assessment: Assessment,
    pathways: AlternativePathwayResult,
    action_candidates: Sequence[ActionCandidate],
    *,
    taxonomy: Taxonomy,
    program: ProgramConfig,
    as_of: date,
    scoring_configuration: LoadedScoringConfiguration | None = None,
) -> ReportStructure:
    """Concise public alias for ``assemble_report``."""
    return assemble_report(
        profile,
        assessment,
        pathways,
        action_candidates,
        taxonomy=taxonomy,
        program=program,
        as_of=as_of,
        scoring_configuration=scoring_configuration,
    )


def _strengths_and_gaps(
    assessment: Assessment,
) -> tuple[list[ReportCompetency], list[ConfirmedGap]]:
    strengths: list[ReportCompetency] = []
    gaps: list[ConfirmedGap] = []
    for trace in assessment.program_alignment.competency_trace:
        if trace.state is EvidenceState.UNKNOWN:
            continue
        if trace.state is EvidenceState.CONFIRMED_ABSENT:
            gaps.append(
                ConfirmedGap(
                    competency_id=trace.competency_id,
                    state=trace.state,
                    demonstrated_level=trace.demonstrated_level,
                    expected_level=trace.expected_level,
                    evidence_ids=trace.evidence_ids,
                    kind=GapKind.CONFIRMED_ABSENT,
                )
            )
            continue
        if trace.state not in {
            EvidenceState.VERIFIED_PRESENT,
            EvidenceState.SELF_REPORTED_PRESENT,
        } or trace.demonstrated_level is None:
            continue
        if trace.demonstrated_level >= trace.expected_level:
            strengths.append(
                ReportCompetency(
                    competency_id=trace.competency_id,
                    state=trace.state,
                    demonstrated_level=trace.demonstrated_level,
                    expected_level=trace.expected_level,
                    evidence_ids=trace.evidence_ids,
                )
            )
        else:
            gaps.append(
                ConfirmedGap(
                    competency_id=trace.competency_id,
                    state=trace.state,
                    demonstrated_level=trace.demonstrated_level,
                    expected_level=trace.expected_level,
                    evidence_ids=trace.evidence_ids,
                    kind=GapKind.BELOW_EXPECTED_LEVEL,
                )
            )
    return strengths, gaps


def _unknowns(assessment: Assessment) -> list[ReportUnknown]:
    trace_by_id = {
        trace.competency_id: trace
        for trace in assessment.program_alignment.competency_trace
    }
    unknowns: list[ReportUnknown] = []
    for field in _ordered_unique(
        [*assessment.not_assessed, *assessment.audit.missing_fields]
    ):
        trace = trace_by_id.get(field)
        demand_weight = trace.demand_weight if trace is not None else None
        unknowns.append(
            ReportUnknown(
                field=field,
                demand_weight=demand_weight,
                needed_to_resolve=f"Provide evidence or a correction for {field}.",
            )
        )
    return unknowns


def _simulate_actions(
    profile: StudentProfile,
    assessment: Assessment,
    candidates: Sequence[ActionCandidate],
    *,
    taxonomy: Taxonomy,
    program: ProgramConfig,
    as_of: date,
    scoring_configuration: LoadedScoringConfiguration,
) -> list[ReportAction]:
    ranked: list[tuple[Fraction, int, ReportAction]] = []
    existing_ids = {evidence.id for evidence in profile.evidence}
    for source_order, candidate in enumerate(candidates):
        if candidate.hypothetical_evidence.id in existing_ids:
            raise ReportError(
                "hypothetical evidence id already exists in the profile: "
                f"{candidate.hypothetical_evidence.id}"
            )
        simulated_profile = profile.model_copy(
            update={
                "evidence": [
                    *profile.evidence,
                    candidate.hypothetical_evidence,
                ]
            }
        )
        competencies = resolve_competencies(
            simulated_profile, taxonomy, as_of=as_of
        )
        simulated = score(
            competencies,
            program,
            taxonomy_version=taxonomy.version,
            engine_version=assessment.audit.engine_version,
            timestamp=assessment.audit.timestamp,
            eligibility=assessment.eligibility,
            preference_fit=assessment.preference_fit,
            admissions_outlook=assessment.admissions_outlook,
            configuration=scoring_configuration,
        )
        changed = _changed_competencies(assessment, simulated)
        action = ReportAction(
            action_id=candidate.action_id,
            title=candidate.title,
            effort=candidate.effort,
            current_band=assessment.pathway_readiness,
            projected_band=simulated.pathway_readiness,
            changed_competencies=changed,
            why=_action_reason(
                candidate,
                assessment.pathway_readiness,
                simulated.pathway_readiness,
                changed,
            ),
        )
        impact = _band_impact(
            assessment.pathway_readiness, simulated.pathway_readiness
        )
        effort = tuple(ActionEffort).index(candidate.effort) + 1
        ranked.append((Fraction(impact, effort), source_order, action))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:MAX_REPORT_ACTIONS]]


def _changed_competencies(
    baseline: Assessment,
    simulated: Assessment,
) -> list[str]:
    baseline_by_id = {
        trace.competency_id: trace
        for trace in baseline.program_alignment.competency_trace
    }
    return [
        trace.competency_id
        for trace in simulated.program_alignment.competency_trace
        if (baseline_trace := baseline_by_id.get(trace.competency_id)) is None
        or baseline_trace.state != trace.state
        or baseline_trace.demonstrated_level != trace.demonstrated_level
        or baseline_trace.match_value != trace.match_value
    ]


def _action_reason(
    candidate: ActionCandidate,
    current_band: ReadinessBand | None,
    projected_band: ReadinessBand | None,
    changed: list[str],
) -> str:
    current = current_band.value if current_band is not None else "NOT_ASSESSED"
    projected = (
        projected_band.value if projected_band is not None else "NOT_ASSESSED"
    )
    changed_text = ", ".join(changed) if changed else "no demanded competency"
    return (
        f"Adding evidence {candidate.hypothetical_evidence.id} changes "
        f"{changed_text}; deterministic rescoring moves the readiness band "
        f"from {current} to {projected}."
    )


def _band_impact(
    current: ReadinessBand | None,
    projected: ReadinessBand | None,
) -> int:
    if current is None or projected is None:
        return 0
    return _BAND_ORDER.index(projected) - _BAND_ORDER.index(current)


def _ordered_unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
