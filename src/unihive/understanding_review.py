"""Source-preserving confirmation adapter (Build Spec sections 4 and 5.1).

Confirmation does not establish semantic support or approve scoring mappings.
Edited statements and excluded claims remain in the receipt for a new review.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from unihive.models import (
    Confidence,
    CoreModel,
    Evidence,
    EvidenceState,
    QualitativeMappingTrace,
    StudentProfile,
)
from unihive.taxonomy import Taxonomy
from unihive.understanding import (
    ClaimAttribution,
    ClaimPresence,
    SourcedClaim,
    UnderstandingResult,
    canonical_json,
    fingerprint,
    supported_context_ids,
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
    presence: ClaimPresence = ClaimPresence.REPORTED_PRESENT
    decision: ClaimDecision
    notes: str = ""


class AcademicCorrection(CoreModel):
    claim_id: str = Field(min_length=1)
    institution: str | None
    qualification: str | None
    grade: str | None
    grade_scale: str | None
    decision: ClaimDecision
    notes: str = ""

    @model_validator(mode="after")
    def reject_blank_values(self) -> AcademicCorrection:
        values = (self.institution, self.qualification, self.grade, self.grade_scale)
        if any(value is not None and not value.strip() for value in values):
            raise ValueError("Academic values must be nonblank or null")
        return self


class JudgmentCorrection(CoreModel):
    judgment_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    decision: ClaimDecision
    notes: str = ""


class UnderstandingReviewRequest(CoreModel):
    profile: StudentProfile
    understanding: UnderstandingResult


def validate_understanding(result: UnderstandingResult, taxonomy_version: str) -> None:
    """Recheck provenance and derived support lists at the import boundary."""
    if result.audit.taxonomy_version != taxonomy_version:
        raise ValueError("Taxonomy changed; analyze the documents again")
    UnderstandingResult.model_validate(result.model_dump(mode="json"))
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
    if (
        supported_context_ids(result.draft, result.support_review)
        != result.supported_context_ids
    ):
        raise ValueError(
            "Understanding context support does not match the support review"
        )


def initial_claim_corrections(result: UnderstandingResult) -> list[ClaimCorrection]:
    """Expose every claim, including duplicates and third-party statements."""
    return [
        ClaimCorrection(
            claim_id=claim.id,
            statement=claim.statement,
            attribution=claim.attribution,
            presence=claim.presence,
            decision=(
                ClaimDecision.CONFIRM
                if claim.id in result.supported_claim_ids
                and claim.attribution == ClaimAttribution.STUDENT
                and claim.presence != ClaimPresence.UNKNOWN
                else ClaimDecision.UNCERTAIN
            ),
        )
        for claim in result.draft.claims
    ]


def initial_academic_corrections(
    result: UnderstandingResult,
) -> list[AcademicCorrection]:
    """Expose every academic record without changing its original scale."""
    claims = {claim.id: claim for claim in result.draft.claims}
    return [
        AcademicCorrection(
            **record.model_dump(),
            decision=(
                ClaimDecision.CONFIRM
                if record.claim_id in result.supported_claim_ids
                and claims[record.claim_id].attribution == ClaimAttribution.STUDENT
                and claims[record.claim_id].presence == ClaimPresence.REPORTED_PRESENT
                else ClaimDecision.UNCERTAIN
            ),
        )
        for record in result.draft.academics
    ]


def initial_judgment_corrections(
    result: UnderstandingResult,
) -> list[JudgmentCorrection]:
    """Require explicit review of every qualitative label before any mapping."""
    return [
        JudgmentCorrection(
            judgment_id=judgment.id,
            label=judgment.label,
            decision=(
                ClaimDecision.CONFIRM
                if judgment.id in result.supported_judgment_ids
                else ClaimDecision.UNCERTAIN
            ),
        )
        for judgment in result.draft.judgments
    ]


def confirm_understanding(
    profile: StudentProfile,
    result: UnderstandingResult,
    corrections: list[ClaimCorrection],
    academic_corrections: list[AcademicCorrection],
    judgment_corrections: list[JudgmentCorrection],
    taxonomy: Taxonomy,
) -> StudentProfile:
    """Project confirmed records using versioned system scoring mappings.

    The original statement and attribution must also qualify: student edits
    cannot override a support check or turn another person's work into credit.
    Grades retain their stated scale and never populate ``normalized_gpa``.
    """
    validate_understanding(result, taxonomy.understanding_version)
    by_id = {change.claim_id: change for change in corrections}
    if len(by_id) != len(corrections) or set(by_id) != {
        claim.id for claim in result.draft.claims
    }:
        raise ValueError("Review every interpreted claim exactly once")
    if any(not change.statement.strip() for change in corrections):
        raise ValueError("Corrected statements must not be blank")
    academic_by_id = {change.claim_id: change for change in academic_corrections}
    academic_ids = {record.claim_id for record in result.draft.academics}
    if (
        len(academic_by_id) != len(academic_corrections)
        or set(academic_by_id) != academic_ids
    ):
        raise ValueError("Review every interpreted academic record exactly once")
    judgment_by_id = {change.judgment_id: change for change in judgment_corrections}
    judgment_ids = {judgment.id for judgment in result.draft.judgments}
    if (
        len(judgment_by_id) != len(judgment_corrections)
        or set(judgment_by_id) != judgment_ids
    ):
        raise ValueError("Review every qualitative judgment exactly once")
    digest = fingerprint(canonical_json(result))
    prefix = f"understanding-{digest}-"
    evidence_ids = {claim.id: prefix + claim.id for claim in result.draft.claims}
    mapped_ids = {
        (mapping.id, claim.id): prefix + f"mapping-{mapping.id}-{claim.id}"
        for mapping in taxonomy.qualitative_mappings
        for claim in result.draft.claims
    }
    generated_ids = set(evidence_ids.values()) | set(mapped_ids.values())
    for item in profile.evidence:
        if item.id in generated_ids and item.source_interpretation_sha256 != digest:
            raise ValueError(
                "Understanding evidence ID conflicts with existing evidence"
            )
    evidence = [
        item for item in profile.evidence if item.source_interpretation_sha256 != digest
    ]
    eligible_claims: set[str] = set()
    for claim in result.draft.claims:
        change = by_id[claim.id]
        if not (
            claim.id in result.supported_claim_ids
            and claim.attribution == ClaimAttribution.STUDENT
            and change.attribution == ClaimAttribution.STUDENT
            and change.decision == ClaimDecision.CONFIRM
            and change.statement == claim.statement
            and change.presence == claim.presence
        ):
            continue
        if claim.presence == ClaimPresence.REPORTED_PRESENT:
            eligible_claims.add(claim.id)
        evidence.append(
            Evidence(
                id=evidence_ids[claim.id],
                kind=claim.category.value,
                raw_text=change.statement,
                state={
                    ClaimPresence.REPORTED_PRESENT: EvidenceState.SELF_REPORTED_PRESENT,
                    ClaimPresence.REPORTED_ABSENT: EvidenceState.CONFIRMED_ABSENT,
                    ClaimPresence.UNKNOWN: EvidenceState.UNKNOWN,
                }[claim.presence],
                quality=None,
                depth=None,
                recency=None,
                source="\n\n".join(
                    f"{citation.document_id}: {citation.quote}"
                    for citation in claim.citations
                ),
                extraction_confidence=Confidence.LOW,
                scoring_exclusion="awaiting_approved_mapping",
                source_interpretation_sha256=digest,
                source_claim_id=claim.id,
            )
        )
    judgments = {
        (item.claim_id, item.dimension): item
        for item in result.draft.judgments
        if item.id in result.supported_judgment_ids
        and judgment_by_id[item.id].decision == ClaimDecision.CONFIRM
        and judgment_by_id[item.id].label == item.label
    }
    rules = {rule.id: rule for rule in taxonomy.evidence_rules}
    claims = {claim.id: claim for claim in result.draft.claims}
    # Highest configured priority wins once per source claim and competency.
    # Repeated labels and overlapping baseline/stronger mappings are not evidence.
    selected: set[tuple[str, str]] = set()
    for mapping in sorted(
        taxonomy.qualitative_mappings, key=lambda item: (-item.priority, item.id)
    ):
        if mapping.rubric_sha256 != result.audit.rubric_sha256:
            continue
        rule = rules[mapping.evidence_rule_id]
        for claim_id in sorted(eligible_claims):
            claim = claims[claim_id]
            key = (claim_id, rule.competency_id)
            suggestion_ids = sorted(
                item.id
                for item in result.draft.competencies
                if item.id in result.supported_competency_ids
                and item.claim_id == claim_id
                and item.competency_id == rule.competency_id
            )
            if key in selected or not suggestion_ids:
                continue
            if claim.category.value != mapping.claim_category or not all(
                (judgment := judgments.get((claim_id, requirement.dimension)))
                is not None
                and judgment.label in requirement.labels
                for requirement in mapping.judgment_requirements
            ):
                continue
            selected.add(key)
            evidence.append(
                Evidence(
                    id=mapped_ids[(mapping.id, claim_id)],
                    kind=rule.evidence_kind,
                    raw_text=by_id[claim_id].statement,
                    state=EvidenceState.SELF_REPORTED_PRESENT,
                    quality=mapping.quality_label,
                    depth=mapping.depth_label,
                    recency=None,
                    source=(
                        f"Configured mapping {mapping.id} "
                        f"({taxonomy.qualitative_mapping_version}); "
                        f"provisional={mapping.provisional}; validated by "
                        f"{mapping.validated_by} on {mapping.validated_on}: "
                        f"{mapping.source}\n\n" + _citation_text(claim)
                    ),
                    extraction_confidence=Confidence.LOW,
                    source_interpretation_sha256=digest,
                    source_claim_id=claim_id,
                    approved_mapping_id=mapping.id,
                    qualitative_mapping=QualitativeMappingTrace(
                        version=taxonomy.qualitative_mapping_version,
                        taxonomy_version=taxonomy.version,
                        mapping_sha256=fingerprint(mapping.model_dump_json()),
                        rubric_sha256=mapping.rubric_sha256,
                        evidence_rule_id=rule.id,
                        provisional=mapping.provisional,
                        judgment_ids=sorted(
                            judgments[(claim_id, requirement.dimension)].id
                            for requirement in mapping.judgment_requirements
                        ),
                        competency_suggestion_ids=suggestion_ids,
                    ),
                )
            )
    academic_history = [
        record
        for record in profile.academic_history
        if record.get("unihive_understanding_sha256") != digest
    ]
    original_academics = {record.claim_id: record for record in result.draft.academics}
    for claim_id in sorted(academic_ids & eligible_claims):
        academic_change = academic_by_id[claim_id]
        if academic_change.decision != ClaimDecision.CONFIRM or not any(
            value is not None
            for value in (
                academic_change.institution,
                academic_change.qualification,
                academic_change.grade,
                academic_change.grade_scale,
            )
        ):
            continue
        original = original_academics[claim_id]
        values = {
            "institution": academic_change.institution,
            "qualification": academic_change.qualification,
            "degree": academic_change.qualification,
            "grade": academic_change.grade,
            "grade_scale": academic_change.grade_scale,
        }
        academic_history.append(
            {
                **values,
                "record_state": (
                    "source_supported"
                    if all(
                        getattr(original, key) == value
                        for key, value in values.items()
                        if key != "degree"
                    )
                    else "student_corrected"
                ),
                "unihive_understanding_sha256": digest,
                "source_claim_id": claim_id,
                "source_citations": [
                    citation.model_dump(mode="json")
                    for citation in claims[claim_id].citations
                ],
            }
        )
    return profile.model_copy(
        update={"evidence": evidence, "academic_history": academic_history}
    )


def _citation_text(claim: SourcedClaim) -> str:
    return "\n\n".join(
        f"{citation.document_id}: {citation.quote}" for citation in claim.citations
    )
