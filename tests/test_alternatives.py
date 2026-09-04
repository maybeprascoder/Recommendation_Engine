"""Tests for the categorical alternative-path rule in Build Spec section 6."""

from __future__ import annotations

from unihive.alternatives import (
    AlternativeCandidate,
    AlternativeSuppressionReason,
    BandDelta,
    ChosenPath,
    evaluate_alternative_pathways,
)
from unihive.models import Confidence, ReadinessBand


def chosen(
    *, readiness_band: ReadinessBand | None = ReadinessBand.DEVELOPING
) -> ChosenPath:
    """Build the student's selected path for categorical rule tests."""
    return ChosenPath(
        path_id="cybersecurity",
        field="Cybersecurity",
        readiness_band=readiness_band,
    )


def candidate(
    path_id: str,
    *,
    readiness_band: ReadinessBand | None = ReadinessBand.STRONG,
    evidence_confidence: Confidence = Confidence.HIGH,
    difference_rests_on_missing_information: bool = False,
    aligned_with_stated_goals: bool = True,
    previously_rejected: bool = False,
) -> AlternativeCandidate:
    """Build a candidate whose defaults satisfy every surfacing condition."""
    return AlternativeCandidate(
        path_id=path_id,
        field=path_id.replace("_", " ").title(),
        readiness_band=readiness_band,
        evidence_confidence=evidence_confidence,
        difference_rests_on_missing_information=(
            difference_rests_on_missing_information
        ),
        aligned_with_stated_goals=aligned_with_stated_goals,
        previously_rejected=previously_rejected,
        reasoning="Existing confirmed evidence is stronger for this path.",
    )


def test_higher_band_alternative_relying_on_unknowns_is_suppressed() -> None:
    result = evaluate_alternative_pathways(
        chosen(),
        [
            candidate(
                "data_science",
                difference_rests_on_missing_information=True,
            )
        ],
    )

    assert result.alternatives == []
    assert result.suppressed[0].reasons == [
        AlternativeSuppressionReason.RELIES_ON_MISSING_INFORMATION
    ]


def test_previously_rejected_field_is_suppressed() -> None:
    result = evaluate_alternative_pathways(
        chosen(), [candidate("data_science", previously_rejected=True)]
    )

    assert result.alternatives == []
    assert AlternativeSuppressionReason.PREVIOUSLY_REJECTED in (
        result.suppressed[0].reasons
    )


def test_more_than_two_candidates_are_truncated_with_a_reason() -> None:
    result = evaluate_alternative_pathways(
        chosen(),
        [
            candidate("data_science"),
            candidate("computer_science"),
            candidate("information_systems"),
        ],
    )

    assert [item.path_id for item in result.alternatives] == [
        "data_science",
        "computer_science",
    ]
    assert result.suppressed[0].path_id == "information_systems"
    assert result.suppressed[0].reasons == [
        AlternativeSuppressionReason.ALTERNATIVE_LIMIT_REACHED
    ]


def test_chosen_path_always_survives() -> None:
    selected = chosen()
    result = evaluate_alternative_pathways(
        selected,
        [
            candidate(
                selected.path_id,
                readiness_band=ReadinessBand.STRONG,
            )
        ],
    )

    assert result.chosen_path is selected
    assert result.chosen_path.path_id == "cybersecurity"
    assert result.alternatives == []
    assert AlternativeSuppressionReason.CHOSEN_PATH in result.suppressed[0].reasons


def test_surface_returns_categorical_delta_and_reasoning() -> None:
    result = evaluate_alternative_pathways(
        chosen(),
        [candidate("computer_science", readiness_band=ReadinessBand.COMPETITIVE)],
    )

    alternative = result.alternatives[0]
    assert alternative.delta is BandDelta.DEVELOPING_TO_COMPETITIVE
    assert alternative.reasoning == (
        "Existing confirmed evidence is stronger for this path."
    )


def test_every_failed_condition_is_recorded_for_debugging() -> None:
    result = evaluate_alternative_pathways(
        chosen(),
        [
            candidate(
                "unrelated_field",
                readiness_band=ReadinessBand.EMERGING,
                evidence_confidence=Confidence.LOW,
                difference_rests_on_missing_information=True,
                aligned_with_stated_goals=False,
                previously_rejected=True,
            )
        ],
    )

    assert result.suppressed[0].reasons == [
        AlternativeSuppressionReason.NOT_A_HIGHER_BAND,
        AlternativeSuppressionReason.EVIDENCE_CONFIDENCE_TOO_LOW,
        AlternativeSuppressionReason.RELIES_ON_MISSING_INFORMATION,
        AlternativeSuppressionReason.NOT_ALIGNED_WITH_STATED_GOALS,
        AlternativeSuppressionReason.PREVIOUSLY_REJECTED,
    ]
