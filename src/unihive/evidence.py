"""Deterministic evaluation of the five evidence attributes.

Implements Build Spec section 4 and Experience Doc section 4, Principle 1.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import ConfigDict, ValidationError, model_validator

from unihive.models import (
    CompetencyLevel,
    CoreModel,
    Evidence,
    EvidenceState,
)
from unihive.taxonomy import EvidenceRule


class EvidenceConfigurationError(ValueError):
    """Raised when the versioned evidence configuration is invalid."""


class EvidenceValueError(ValueError):
    """Raised when present evidence cannot be evaluated from configured values."""


class RecencyBand(CoreModel):
    """A configured recency multiplier through an optional maximum age."""

    max_age_days: int | None
    factor: Decimal


class RecencyConfiguration(CoreModel):
    """Configured handling for dated and undated evidence."""

    undated_factor: Decimal
    bands: tuple[RecencyBand, ...]


class TailMode(StrEnum):
    CONSTANT = "constant"
    GEOMETRIC = "geometric"


class CombinationCurve(CoreModel):
    """Rank multipliers used to combine evidence with diminishing returns."""

    multipliers: tuple[Decimal, ...]
    tail_multiplier: Decimal
    tail_mode: TailMode = TailMode.CONSTANT

    def multiplier_at(self, index: int) -> Decimal:
        """Extend the configured curve without inventing a new decay weight."""
        if index < len(self.multipliers):
            return self.multipliers[index]
        if self.tail_mode == TailMode.CONSTANT or not self.tail_multiplier:
            return self.tail_multiplier
        ratio = self.tail_multiplier / self.multipliers[-1]
        return self.tail_multiplier * ratio ** (index - len(self.multipliers))


class EvidenceConfiguration(CoreModel):
    """All configured values used by deterministic evidence evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provisional: bool
    validated_by: str | None
    source: str | None
    quality_ladders: dict[str, dict[str, Decimal]]
    default_depth_label: str
    depth_factors: dict[str, Decimal]
    verification_factors: dict[EvidenceState, Decimal]
    recency: RecencyConfiguration
    combination_curve: CombinationCurve
    level_thresholds: dict[str, Decimal]

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        """Reject incomplete or non-monotonic evidence configuration."""
        if self.default_depth_label not in self.depth_factors:
            raise ValueError("default_depth_label is absent from depth_factors")

        present_states = {
            EvidenceState.VERIFIED_PRESENT,
            EvidenceState.SELF_REPORTED_PRESENT,
        }
        missing_states = present_states - self.verification_factors.keys()
        if missing_states:
            names = ", ".join(sorted(state.value for state in missing_states))
            raise ValueError(f"missing verification factors: {names}")

        bands = self.recency.bands
        if not bands or bands[-1].max_age_days is not None:
            raise ValueError("recency bands must end with an open-ended band")
        finite_limits = [
            band.max_age_days for band in bands if band.max_age_days is not None
        ]
        if any(band.max_age_days is None for band in bands[:-1]):
            raise ValueError("only the final recency band may be open-ended")
        if finite_limits != sorted(set(finite_limits)):
            raise ValueError("finite recency bands must be strictly increasing")

        multipliers = self.combination_curve.multipliers
        if not multipliers:
            raise ValueError("combination curve must contain a multiplier")
        if any(
            later > earlier
            for earlier, later in zip(multipliers, multipliers[1:], strict=False)
        ):
            raise ValueError("combination multipliers must not increase")
        if self.combination_curve.tail_multiplier > multipliers[-1]:
            raise ValueError("tail multiplier must not exceed the final multiplier")
        if (
            self.combination_curve.tail_mode == TailMode.GEOMETRIC
            and self.combination_curve.tail_multiplier
            and self.combination_curve.tail_multiplier >= multipliers[-1]
        ):
            raise ValueError("geometric tail must decrease from the final multiplier")

        expected_levels = {level.name for level in CompetencyLevel}
        if self.level_thresholds.keys() != expected_levels:
            raise ValueError("level_thresholds must define every CompetencyLevel")
        ordered_thresholds = [
            self.level_thresholds[level.name] for level in CompetencyLevel
        ]
        if ordered_thresholds != sorted(set(ordered_thresholds)):
            raise ValueError("competency thresholds must be strictly increasing")
        return self


class EvidenceEvaluation(CoreModel):
    """Configured attribute values before cross-evidence combination."""

    evidence_id: str
    rule_id: str
    state: EvidenceState
    quality: Decimal
    relevance: Decimal
    depth: Decimal
    verification: Decimal
    recency: Decimal
    raw_contribution: Decimal


def load_evidence_configuration(
    document: Mapping[str, object],
) -> EvidenceConfiguration:
    """Parse the schema-validated ladders document into typed configuration."""
    try:
        return EvidenceConfiguration.model_validate(document)
    except ValidationError as error:
        raise EvidenceConfigurationError(str(error)) from error


def evaluate_evidence(
    evidence: Evidence,
    rule: EvidenceRule,
    configuration: EvidenceConfiguration,
    *,
    as_of: date,
) -> EvidenceEvaluation:
    """Evaluate quality, relevance, depth, verification, and recency."""
    if evidence.scoring_exclusion is not None:
        raise EvidenceValueError(
            "Evidence requires a configured/approved scoring mapping"
        )
    if (
        evidence.qualitative_mapping is not None
        and evidence.qualitative_mapping.evidence_rule_id != rule.id
    ):
        raise EvidenceValueError(
            "Mapped evidence cannot be routed through another rule"
        )
    if evidence.state not in configuration.verification_factors:
        raise EvidenceValueError(
            f"Evidence {evidence.id} is not in a present state and cannot be scored"
        )
    if evidence.quality is None:
        raise EvidenceValueError(f"Evidence {evidence.id} has no quality label")

    try:
        quality_ladder = configuration.quality_ladders[rule.quality_ladder]
        quality = quality_ladder[_normalize_label(evidence.quality)]
    except KeyError as error:
        raise EvidenceValueError(
            f"Evidence {evidence.id} has an unconfigured quality value"
        ) from error

    depth_label = _normalize_label(evidence.depth or configuration.default_depth_label)
    try:
        depth = configuration.depth_factors[depth_label]
    except KeyError as error:
        raise EvidenceValueError(
            f"Evidence {evidence.id} has an unconfigured depth value"
        ) from error

    verification = configuration.verification_factors[evidence.state]
    recency = _recency_factor(evidence, configuration, as_of=as_of)
    raw_contribution = quality * rule.relevance * depth * verification * recency
    return EvidenceEvaluation(
        evidence_id=evidence.id,
        rule_id=rule.id,
        state=evidence.state,
        quality=quality,
        relevance=rule.relevance,
        depth=depth,
        verification=verification,
        recency=recency,
        raw_contribution=raw_contribution,
    )


def _recency_factor(
    evidence: Evidence,
    configuration: EvidenceConfiguration,
    *,
    as_of: date,
) -> Decimal:
    if evidence.recency is None:
        return configuration.recency.undated_factor

    age_days = (as_of - evidence.recency).days
    if age_days < 0:
        raise EvidenceValueError(
            f"Evidence {evidence.id} is dated after the as_of date"
        )
    for band in configuration.recency.bands:
        if band.max_age_days is None or age_days <= band.max_age_days:
            return band.factor
    raise EvidenceConfigurationError("recency configuration has no matching band")


def _normalize_label(label: str) -> str:
    return "_".join(label.casefold().replace("-", " ").split())
