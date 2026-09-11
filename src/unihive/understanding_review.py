"""Source-preserving confirmation adapter (Build Spec sections 4 and 5.1).

Confirmation does not establish semantic support or approve scoring mappings.
Edited statements and excluded claims remain in the receipt for a new review.
"""

from enum import StrEnum

from pydantic import Field

from unihive.models import (
    Confidence,
    CoreModel,
    Evidence,
    EvidenceState,
    StudentProfile,
)
from unihive.understanding import (
    ClaimAttribution,
    UnderstandingResult,
    canonical_json,
    fingerprint,
    supported_ids,
    validate_draft,
)


class ClaimDecision(StrEnum):
    CONFIRM = "confirm"
    EXCLUDE = "exclude"
    UNCERTAIN = "uncertain"


class ClaimCorrection(CoreModel):
    claim_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    attribution: ClaimAttribution
    decision: ClaimDecision
    notes: str = ""


class UnderstandingReviewRequest(CoreModel):
    profile: StudentProfile
    understanding: UnderstandingResult


def validate_understanding(result: UnderstandingResult, taxonomy_version: str) -> None:
    """Recheck provenance and derived support lists at the import boundary."""
    if result.audit.taxonomy_version != taxonomy_version:
        raise ValueError("Taxonomy changed; analyze the documents again")
    validate_draft(
        result.draft,
        result.documents,
        result.audit.rubric_snapshot,
        result.audit.competency_catalog,
    )
    if result.audit.source_sha256 != {
        doc.id: fingerprint(doc.text) for doc in result.documents
    }:
        raise ValueError("Understanding source hashes do not match the documents")
    if result.audit.rubric_sha256 != fingerprint(
        canonical_json(result.audit.rubric_snapshot)
    ):
        raise ValueError("Understanding rubric hash does not match its snapshot")
    actual = supported_ids(result.draft, result.support_review)
    expected = (
        result.supported_claim_ids,
        result.supported_judgment_ids,
        result.supported_competency_ids,
    )
    if actual != expected:
        raise ValueError("Understanding support lists do not match the support review")


def initial_claim_corrections(result: UnderstandingResult) -> list[ClaimCorrection]:
    """Expose every claim, including duplicates and third-party statements."""
    return [
        ClaimCorrection(
            claim_id=claim.id,
            statement=claim.statement,
            attribution=claim.attribution,
            decision=(
                ClaimDecision.CONFIRM
                if claim.id in result.supported_claim_ids
                and claim.attribution == ClaimAttribution.STUDENT
                else ClaimDecision.UNCERTAIN
            ),
        )
        for claim in result.draft.claims
    ]


def confirm_understanding(
    profile: StudentProfile,
    result: UnderstandingResult,
    corrections: list[ClaimCorrection],
    taxonomy_version: str,
) -> StudentProfile:
    """Import only confirmed, canonical, supported student claims, without scores.

    The original statement and attribution must also qualify: student edits
    cannot override a support check or turn another person's work into credit.
    Academic records and qualitative judgments stay in the interpretation receipt.
    """
    validate_understanding(result, taxonomy_version)
    by_id = {change.claim_id: change for change in corrections}
    if len(by_id) != len(corrections) or set(by_id) != {
        claim.id for claim in result.draft.claims
    }:
        raise ValueError("Review every interpreted claim exactly once")
    if any(not change.statement.strip() for change in corrections):
        raise ValueError("Corrected statements must not be blank")
    digest = fingerprint(canonical_json(result))
    evidence_ids = {
        claim.id: f"understanding-{digest}-{claim.id}" for claim in result.draft.claims
    }
    # Re-confirmation replaces this interpretation's imports, never duplicates them.
    for item in profile.evidence:
        if item.id in evidence_ids.values() and (
            item.scoring_exclusion != "awaiting_approved_mapping"
        ):
            raise ValueError(
                "Understanding evidence ID conflicts with existing evidence"
            )
    evidence = [
        item for item in profile.evidence if item.id not in evidence_ids.values()
    ]
    for claim in result.draft.claims:
        change = by_id[claim.id]
        if not (
            claim.id in result.supported_claim_ids
            and claim.attribution == ClaimAttribution.STUDENT
            and change.attribution == ClaimAttribution.STUDENT
            and change.decision == ClaimDecision.CONFIRM
            and change.statement == claim.statement
        ):
            continue
        evidence.append(
            Evidence(
                id=evidence_ids[claim.id],
                kind=claim.category.value,
                raw_text=change.statement,
                state=EvidenceState.SELF_REPORTED_PRESENT,
                quality=None,
                depth=None,
                recency=None,
                source="\n\n".join(
                    f"{citation.document_id}: {citation.quote}"
                    for citation in claim.citations
                ),
                extraction_confidence=Confidence.LOW,
                scoring_exclusion="awaiting_approved_mapping",
            )
        )
    return profile.model_copy(update={"evidence": evidence})
