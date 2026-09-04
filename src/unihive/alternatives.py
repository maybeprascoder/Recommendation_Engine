"""Categorical alternative-path evaluation.

Implements Build Spec section 6 without comparing continuous readiness values.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from unihive.models import Confidence, CoreModel, ReadinessBand

MAX_ALTERNATIVES: Final = 2


class BandDelta(StrEnum):
    """Every categorical upward transition between readiness bands."""

    EMERGING_TO_DEVELOPING = "EMERGING_TO_DEVELOPING"
    EMERGING_TO_COMPETITIVE = "EMERGING_TO_COMPETITIVE"
    EMERGING_TO_STRONG = "EMERGING_TO_STRONG"
    DEVELOPING_TO_COMPETITIVE = "DEVELOPING_TO_COMPETITIVE"
    DEVELOPING_TO_STRONG = "DEVELOPING_TO_STRONG"
    COMPETITIVE_TO_STRONG = "COMPETITIVE_TO_STRONG"


class AlternativeSuppressionReason(StrEnum):
    """Categorical reasons that a related pathway was not surfaced."""

    CHOSEN_PATH = "CHOSEN_PATH"
    READINESS_BAND_UNAVAILABLE = "READINESS_BAND_UNAVAILABLE"
    NOT_A_HIGHER_BAND = "NOT_A_HIGHER_BAND"
    EVIDENCE_CONFIDENCE_TOO_LOW = "EVIDENCE_CONFIDENCE_TOO_LOW"
    RELIES_ON_MISSING_INFORMATION = "RELIES_ON_MISSING_INFORMATION"
    NOT_ALIGNED_WITH_STATED_GOALS = "NOT_ALIGNED_WITH_STATED_GOALS"
    PREVIOUSLY_REJECTED = "PREVIOUSLY_REJECTED"
    ALTERNATIVE_LIMIT_REACHED = "ALTERNATIVE_LIMIT_REACHED"


class ChosenPath(CoreModel):
    """The student's selected pathway, which this rule never replaces."""

    path_id: str
    field: str
    readiness_band: ReadinessBand | None


class AlternativeCandidate(CoreModel):
    """Explicit facts needed to evaluate one related pathway."""

    path_id: str
    field: str
    readiness_band: ReadinessBand | None
    evidence_confidence: Confidence
    difference_rests_on_missing_information: bool
    aligned_with_stated_goals: bool
    previously_rejected: bool
    reasoning: str


class SurfacedAlternative(CoreModel):
    """An alternative satisfying every categorical surfacing condition."""

    path_id: str
    field: str
    readiness_band: ReadinessBand
    evidence_confidence: Confidence
    delta: BandDelta
    reasoning: str


class SuppressedAlternative(CoreModel):
    """A filtered candidate and every categorical reason it was suppressed."""

    path_id: str
    field: str
    reasons: list[AlternativeSuppressionReason]


class AlternativePathwayResult(CoreModel):
    """The preserved chosen path plus surfaced and suppressed candidates."""

    chosen_path: ChosenPath
    alternatives: list[SurfacedAlternative]
    suppressed: list[SuppressedAlternative]


_BAND_DELTAS: Final[dict[tuple[ReadinessBand, ReadinessBand], BandDelta]] = {
    (
        ReadinessBand.EMERGING,
        ReadinessBand.DEVELOPING,
    ): BandDelta.EMERGING_TO_DEVELOPING,
    (
        ReadinessBand.EMERGING,
        ReadinessBand.COMPETITIVE,
    ): BandDelta.EMERGING_TO_COMPETITIVE,
    (
        ReadinessBand.EMERGING,
        ReadinessBand.STRONG,
    ): BandDelta.EMERGING_TO_STRONG,
    (
        ReadinessBand.DEVELOPING,
        ReadinessBand.COMPETITIVE,
    ): BandDelta.DEVELOPING_TO_COMPETITIVE,
    (
        ReadinessBand.DEVELOPING,
        ReadinessBand.STRONG,
    ): BandDelta.DEVELOPING_TO_STRONG,
    (
        ReadinessBand.COMPETITIVE,
        ReadinessBand.STRONG,
    ): BandDelta.COMPETITIVE_TO_STRONG,
}


def evaluate_alternative_pathways(
    chosen_path: ChosenPath,
    candidates: Sequence[AlternativeCandidate],
) -> AlternativePathwayResult:
    """Implement Build Spec §6's categorical alternative-path rule.

    Candidates retain their input order. This lets an upstream related-path
    discovery step supply a deterministic order without this rule inventing an
    additional ranking signal.
    """
    alternatives: list[SurfacedAlternative] = []
    suppressed: list[SuppressedAlternative] = []

    for candidate in candidates:
        reasons = _suppression_reasons(chosen_path, candidate)
        delta = _band_delta(chosen_path.readiness_band, candidate.readiness_band)

        if reasons:
            suppressed.append(_suppressed(candidate, reasons))
            continue
        if delta is None or candidate.readiness_band is None:
            raise AlternativePathwayError(
                "A candidate without a categorical upward delta passed filtering"
            )
        if len(alternatives) >= MAX_ALTERNATIVES:
            suppressed.append(
                _suppressed(
                    candidate,
                    [AlternativeSuppressionReason.ALTERNATIVE_LIMIT_REACHED],
                )
            )
            continue

        alternatives.append(
            SurfacedAlternative(
                path_id=candidate.path_id,
                field=candidate.field,
                readiness_band=candidate.readiness_band,
                evidence_confidence=candidate.evidence_confidence,
                delta=delta,
                reasoning=candidate.reasoning,
            )
        )

    return AlternativePathwayResult(
        chosen_path=chosen_path,
        alternatives=alternatives,
        suppressed=suppressed,
    )


def surface_alternatives(
    chosen_path: ChosenPath,
    candidates: Sequence[AlternativeCandidate],
) -> AlternativePathwayResult:
    """Concise public alias for ``evaluate_alternative_pathways``."""
    return evaluate_alternative_pathways(chosen_path, candidates)


class AlternativePathwayError(ValueError):
    """Raised when categorical alternative evaluation is internally invalid."""


def _suppression_reasons(
    chosen_path: ChosenPath,
    candidate: AlternativeCandidate,
) -> list[AlternativeSuppressionReason]:
    reasons: list[AlternativeSuppressionReason] = []

    if candidate.path_id == chosen_path.path_id:
        reasons.append(AlternativeSuppressionReason.CHOSEN_PATH)

    if (
        chosen_path.readiness_band is None
        or candidate.readiness_band is None
    ):
        reasons.append(AlternativeSuppressionReason.READINESS_BAND_UNAVAILABLE)
    elif _band_delta(
        chosen_path.readiness_band, candidate.readiness_band
    ) is None:
        reasons.append(AlternativeSuppressionReason.NOT_A_HIGHER_BAND)

    if candidate.evidence_confidence is Confidence.LOW:
        reasons.append(AlternativeSuppressionReason.EVIDENCE_CONFIDENCE_TOO_LOW)
    if candidate.difference_rests_on_missing_information:
        reasons.append(
            AlternativeSuppressionReason.RELIES_ON_MISSING_INFORMATION
        )
    if not candidate.aligned_with_stated_goals:
        reasons.append(
            AlternativeSuppressionReason.NOT_ALIGNED_WITH_STATED_GOALS
        )
    if candidate.previously_rejected:
        reasons.append(AlternativeSuppressionReason.PREVIOUSLY_REJECTED)

    return reasons


def _band_delta(
    chosen_band: ReadinessBand | None,
    candidate_band: ReadinessBand | None,
) -> BandDelta | None:
    if chosen_band is None or candidate_band is None:
        return None
    return _BAND_DELTAS.get((chosen_band, candidate_band))


def _suppressed(
    candidate: AlternativeCandidate,
    reasons: list[AlternativeSuppressionReason],
) -> SuppressedAlternative:
    return SuppressedAlternative(
        path_id=candidate.path_id,
        field=candidate.field,
        reasons=reasons,
    )
