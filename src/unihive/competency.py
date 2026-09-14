"""Resolve student evidence into program-independent competencies.

Implements Build Spec section 4 and Experience Doc section 4, Principle 1.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from unihive.evidence import (
    EvidenceConfiguration,
    EvidenceEvaluation,
    evaluate_evidence,
    load_evidence_configuration,
)
from unihive.models import (
    CompetencyLevel,
    Evidence,
    EvidenceContribution,
    EvidenceState,
    StudentCompetency,
    StudentProfile,
)
from unihive.taxonomy import EvidenceRule, Taxonomy

PRESENT_STATES = {
    EvidenceState.VERIFIED_PRESENT,
    EvidenceState.SELF_REPORTED_PRESENT,
}


def resolve_competencies(
    profile: StudentProfile,
    taxonomy: Taxonomy,
    *,
    as_of: date,
) -> list[StudentCompetency]:
    """Resolve every taxonomy node without consulting any program configuration."""
    configuration = load_evidence_configuration(taxonomy.evidence_configuration)
    evidence_by_kind = _group_evidence_by_kind(profile.evidence)
    rules_by_competency = _group_rules_by_competency(taxonomy.evidence_rules)

    return [
        _resolve_one(
            competency_id,
            rules_by_competency.get(competency_id, ()),
            evidence_by_kind,
            configuration,
            as_of=as_of,
        )
        for competency_id in sorted(node.id for node in taxonomy.competencies)
    ]


def _resolve_one(
    competency_id: str,
    rules: tuple[EvidenceRule, ...],
    evidence_by_kind: dict[str, tuple[Evidence, ...]],
    configuration: EvidenceConfiguration,
    *,
    as_of: date,
) -> StudentCompetency:
    matches = [
        (evidence, rule)
        for rule in rules
        for evidence in evidence_by_kind.get(rule.evidence_kind, ())
        if evidence.qualitative_mapping is None
        or evidence.qualitative_mapping.evidence_rule_id == rule.id
    ]
    evaluations = [
        evaluate_evidence(evidence, rule, configuration, as_of=as_of)
        for evidence, rule in matches
        if evidence.state in PRESENT_STATES
    ]
    evaluations.sort(
        key=lambda item: (-item.raw_contribution, item.evidence_id, item.rule_id)
    )

    present_trace, total = _combine_present_evidence(evaluations, configuration)
    non_present_trace = [
        _non_present_trace(evidence, rule)
        for evidence, rule in sorted(
            matches, key=lambda item: (item[0].id, item[1].id)
        )
        if evidence.state not in PRESENT_STATES
    ]
    trace = present_trace + non_present_trace
    contributing_ids = sorted({entry.evidence_id for entry in trace})

    if evaluations:
        state = (
            EvidenceState.VERIFIED_PRESENT
            if any(item.state is EvidenceState.VERIFIED_PRESENT for item in evaluations)
            else EvidenceState.SELF_REPORTED_PRESENT
        )
        level = _level_for(total, configuration)
    elif any(
        evidence.state is EvidenceState.CONFIRMED_ABSENT
        for evidence, _ in matches
    ):
        state = EvidenceState.CONFIRMED_ABSENT
        level = None
    elif matches and all(
        evidence.state is EvidenceState.NOT_APPLICABLE for evidence, _ in matches
    ):
        state = EvidenceState.NOT_APPLICABLE
        level = None
    else:
        state = EvidenceState.UNKNOWN
        level = None

    return StudentCompetency(
        competency_id=competency_id,
        level=level,
        state=state,
        contributing_evidence_ids=contributing_ids,
        explanation_trace=trace,
    )


def _combine_present_evidence(
    evaluations: list[EvidenceEvaluation],
    configuration: EvidenceConfiguration,
) -> tuple[list[EvidenceContribution], Decimal]:
    trace: list[EvidenceContribution] = []
    total = Decimal("0")
    for index, evaluation in enumerate(evaluations):
        multiplier = configuration.combination_curve.multiplier_at(index)
        contribution = evaluation.raw_contribution * multiplier
        total += contribution
        trace.append(
            EvidenceContribution(
                evidence_id=evaluation.evidence_id,
                rule_id=evaluation.rule_id,
                state=evaluation.state,
                quality=evaluation.quality,
                relevance=evaluation.relevance,
                depth=evaluation.depth,
                verification=evaluation.verification,
                recency=evaluation.recency,
                combination_multiplier=multiplier,
                contribution=contribution,
            )
        )
    return trace, total


def _non_present_trace(
    evidence: Evidence, rule: EvidenceRule
) -> EvidenceContribution:
    return EvidenceContribution(
        evidence_id=evidence.id,
        rule_id=rule.id,
        state=evidence.state,
        quality=None,
        relevance=None,
        depth=None,
        verification=None,
        recency=None,
        combination_multiplier=None,
        contribution=None,
    )


def _level_for(
    total: Decimal, configuration: EvidenceConfiguration
) -> CompetencyLevel | None:
    for level in reversed(CompetencyLevel):
        if total >= configuration.level_thresholds[level.name]:
            return level
    return None


def _group_evidence_by_kind(
    evidence_items: list[Evidence],
) -> dict[str, tuple[Evidence, ...]]:
    grouped: dict[str, list[Evidence]] = {}
    for evidence in sorted(evidence_items, key=lambda item: item.id):
        if evidence.scoring_exclusion is not None:
            continue
        grouped.setdefault(evidence.kind, []).append(evidence)
    return {kind: tuple(items) for kind, items in grouped.items()}


def _group_rules_by_competency(
    rules: tuple[EvidenceRule, ...],
) -> dict[str, tuple[EvidenceRule, ...]]:
    grouped: dict[str, list[EvidenceRule]] = {}
    for rule in sorted(rules, key=lambda item: item.id):
        grouped.setdefault(rule.competency_id, []).append(rule)
    return {competency_id: tuple(items) for competency_id, items in grouped.items()}
