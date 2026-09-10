"""Student corrections must not manufacture verification or erase unknowns."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from unihive.models import EvidenceState, StudentProfile
from unihive.review import ConfirmationRequest, confirm_evidence
from unihive.taxonomy import Taxonomy, load_taxonomy


@pytest.fixture
def taxonomy() -> Taxonomy:
    return load_taxonomy()


def submission(taxonomy: Taxonomy, **changes: object) -> ConfirmationRequest:
    profile = json.loads(
        (Path(__file__).parent / "fixtures/cli/profile.json").read_text()
    )
    evidence = profile["evidence"][0]
    correction = {
        key: evidence[key]
        for key in ("raw_text", "kind", "state", "quality", "depth", "recency")
    }
    correction.update(changes)
    return ConfirmationRequest.model_validate_json(
        json.dumps(
            {
                "profile": profile,
                "taxonomy_version": taxonomy.version,
                "confirmed": True,
                "corrections": [{"evidence_id": evidence["id"], **correction}],
            }
        ),
        strict=True,
    )


def test_unchanged_review_preserves_profile(taxonomy: Taxonomy) -> None:
    request = submission(taxonomy)
    assert confirm_evidence(request, taxonomy) == request.profile


@pytest.mark.parametrize(
    "changes",
    [
        {"raw_text": "Corrected paper claim — 学生"},
        {"quality": "preprint"},
        {"depth": "contributor"},
        {"recency": "2025-01-01"},
        {"kind": "coursework"},
    ],
)
def test_edits_downgrade_verification_preserving_source(
    taxonomy: Taxonomy,
    changes: dict[str, object],
) -> None:
    request = submission(taxonomy, **changes)
    original = request.profile.model_dump_json()
    corrected = confirm_evidence(request, taxonomy).evidence[0]
    assert corrected.state == EvidenceState.SELF_REPORTED_PRESENT
    assert corrected.source == request.profile.evidence[0].source
    assert (
        corrected.extraction_confidence
        == request.profile.evidence[0].extraction_confidence
    )
    assert request.profile.model_dump_json() == original


@pytest.mark.parametrize("state", ["UNKNOWN", "CONFIRMED_ABSENT", "NOT_APPLICABLE"])
def test_nonpresent_states_remain_distinct(taxonomy: Taxonomy, state: str) -> None:
    corrected = confirm_evidence(submission(taxonomy, state=state), taxonomy).evidence[
        0
    ]
    assert corrected.state.value == state
    assert corrected.quality is None and corrected.depth is None


def test_cannot_promote_self_report_to_verified(taxonomy: Taxonomy) -> None:
    request = submission(taxonomy)
    data = request.model_dump(mode="json")
    data["profile"]["evidence"][0]["state"] = "SELF_REPORTED_PRESENT"
    request = ConfirmationRequest.model_validate_json(json.dumps(data), strict=True)
    assert (
        confirm_evidence(request, taxonomy).evidence[0].state
        == EvidenceState.SELF_REPORTED_PRESENT
    )


@pytest.mark.parametrize("bad", [False, "true", 1])
def test_requires_explicit_boolean_confirmation(
    taxonomy: Taxonomy, bad: object
) -> None:
    data = submission(taxonomy).model_dump(mode="json")
    data["confirmed"] = bad
    with pytest.raises(ValueError):
        confirm_evidence(
            ConfirmationRequest.model_validate_json(json.dumps(data)), taxonomy
        )


@pytest.mark.parametrize(
    "mode", ["missing", "duplicate", "foreign", "source", "confidence", "taxonomy"]
)
def test_rejects_incomplete_or_forged_review(taxonomy: Taxonomy, mode: str) -> None:
    data = submission(taxonomy).model_dump(mode="json")
    if mode == "missing":
        data["corrections"] = []
    elif mode == "duplicate":
        data["corrections"] *= 2
    elif mode == "foreign":
        data["corrections"][0]["evidence_id"] = "other"
    elif mode == "source":
        data["corrections"][0]["source"] = "Fabricated source"
    elif mode == "confidence":
        data["corrections"][0]["extraction_confidence"] = "HIGH"
    else:
        data["taxonomy_version"] = "stale"
    with pytest.raises(ValueError):
        confirm_evidence(
            ConfirmationRequest.model_validate_json(json.dumps(data)), taxonomy
        )


def test_unknown_kind_is_allowed_but_invalid_mapped_labels_are_rejected(
    taxonomy: Taxonomy,
) -> None:
    assert confirm_evidence(submission(taxonomy, kind="coursework"), taxonomy)
    with pytest.raises(ValueError, match="quality"):
        confirm_evidence(submission(taxonomy, quality="invented"), taxonomy)
    with pytest.raises(ValueError, match="depth"):
        confirm_evidence(submission(taxonomy, depth="invented"), taxonomy)


def test_empty_profile_can_confirm_without_inventing_evidence(
    taxonomy: Taxonomy,
) -> None:
    request = submission(taxonomy)
    data = request.profile.model_dump()
    data["evidence"] = []
    profile = StudentProfile.model_validate(data)
    result = confirm_evidence(
        ConfirmationRequest(
            profile=profile,
            corrections=[],
            confirmed=True,
            taxonomy_version=taxonomy.version,
        ),
        taxonomy,
    )
    assert result.evidence == []


def test_source_is_not_an_editable_field(taxonomy: Taxonomy) -> None:
    with pytest.raises(ValidationError):
        submission(taxonomy, source="New source")
