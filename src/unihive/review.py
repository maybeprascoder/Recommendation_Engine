"""Deterministic evidence corrections, separate from document verification."""

from datetime import date
from decimal import Decimal

from pydantic import Field, StrictBool

from unihive.models import (
    Confidence,
    CoreModel,
    Evidence,
    EvidenceState,
    StructuredRecord,
    StudentProfile,
)
from unihive.taxonomy import Taxonomy


class EvidenceCorrection(CoreModel):
    evidence_id: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    state: EvidenceState
    quality: str | None
    depth: str | None
    recency: date | None


class ProfileDetails(CoreModel):
    """Editable profile fields from Build Spec section 5.1; no evidence override."""

    academic_history: list[StructuredRecord]
    normalized_gpa: Decimal | None = Field(ge=0, allow_inf_nan=False)
    courses: list[StructuredRecord]
    skills: list[str]
    projects: list[StructuredRecord]
    research: list[StructuredRecord]
    work: list[StructuredRecord]
    goals: list[str]
    constraints: list[str]
    tests: list[StructuredRecord]
    citizenship: str | None
    residency: str | None


class ConfirmationRequest(CoreModel):
    profile: StudentProfile
    taxonomy_version: str
    corrections: list[EvidenceCorrection]
    confirmed: StrictBool
    profile_details: ProfileDetails | None = None
    additions: list[EvidenceCorrection] = Field(default_factory=list)


def confirm_evidence(
    request: ConfirmationRequest, taxonomy: Taxonomy
) -> StudentProfile:
    """Preserve provenance; student edits can never confer verified status."""
    if not request.confirmed:
        raise ValueError("Explicit evidence confirmation is required")
    if request.taxonomy_version != taxonomy.version:
        raise ValueError("Taxonomy changed; reload the evidence review")
    original = {item.id: item for item in request.profile.evidence}
    ids = [item.evidence_id for item in request.corrections]
    if len(original) != len(request.profile.evidence):
        raise ValueError("Original evidence IDs must be unique")
    if len(set(ids)) != len(ids) or set(ids) != set(original):
        raise ValueError("Review every original evidence item exactly once")
    added_ids = [item.evidence_id for item in request.additions]
    if len(set(added_ids)) != len(added_ids) or set(added_ids) & set(original):
        raise ValueError("New evidence IDs must be unique and separate from originals")
    corrected: list[Evidence] = []
    ladders = taxonomy.evidence_configuration["quality_ladders"]
    depths = taxonomy.evidence_configuration["depth_factors"]
    assert isinstance(ladders, dict) and isinstance(depths, dict)
    for change in [*request.corrections, *request.additions]:
        before = original.get(change.evidence_id)
        if before is None:
            # A manual claim is provenance, not an extracted or verified document.
            before = Evidence(
                id=change.evidence_id,
                kind=change.kind,
                raw_text=change.raw_text,
                state=EvidenceState.SELF_REPORTED_PRESENT,
                quality=None,
                depth=None,
                recency=change.recency,
                source="Student supplied: " + change.raw_text,
                extraction_confidence=Confidence.LOW,
            )
        fields = change.model_dump(exclude={"evidence_id"})
        state = change.state
        changed = any(getattr(before, key) != value for key, value in fields.items())
        if state == EvidenceState.VERIFIED_PRESENT and (
            changed or before.state != EvidenceState.VERIFIED_PRESENT
        ):
            state = EvidenceState.SELF_REPORTED_PRESENT
        fields["state"] = state
        if state in {
            EvidenceState.VERIFIED_PRESENT,
            EvidenceState.SELF_REPORTED_PRESENT,
        }:
            if not change.raw_text.strip() or not change.kind.strip():
                raise ValueError("Present evidence requires a claim and kind")
            for rule in taxonomy.evidence_rules:
                if rule.evidence_kind == change.kind:
                    ladder = ladders[rule.quality_ladder]
                    assert isinstance(ladder, dict)
                    if change.quality is not None and change.quality not in ladder:
                        raise ValueError(f"Unsupported quality for {change.kind}")
                    if change.depth is not None and change.depth not in depths:
                        raise ValueError("Unsupported evidence depth")
        else:
            fields.update(quality=None, depth=None)
        corrected.append(Evidence.model_validate({**before.model_dump(), **fields}))
    # Keep original ordering so reordering the form cannot affect replay.
    by_id = {item.id: item for item in corrected}
    return StudentProfile.model_validate(
        {
            **request.profile.model_dump(),
            **(request.profile_details.model_dump() if request.profile_details else {}),
            "evidence": [by_id[item.id] for item in request.profile.evidence]
            + [by_id[identifier] for identifier in sorted(added_ids)],
        }
    )
