"""Generic, source-linked evidence contracts (Build Spec sections 4 and 5.1).

These are proposed qualitative judgments, not competency levels or admissions
scores. Keeping them separate prevents unreviewed LLM labels entering arithmetic.
"""

from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, model_validator

from unihive.models import CoreModel
from unihive.resources import DATA_ROOT

Text = Annotated[str, Field(min_length=1)]


class SourceDocument(CoreModel):
    id: Text
    text: Text


class Citation(CoreModel):
    document_id: Text
    quote: Text


class EvidenceCategory(StrEnum):
    PROJECT = "project"
    WORK = "work"
    RESEARCH = "research"
    PUBLICATION = "publication"
    COURSEWORK = "coursework"
    EDUCATION = "education"
    ACTIVITY = "activity"
    OTHER = "other"


class ClaimAttribution(StrEnum):
    STUDENT = "student"
    TEAM = "team"
    OTHER = "other"
    UNKNOWN = "unknown"


class ClaimPresence(StrEnum):
    REPORTED_PRESENT = "reported_present"
    REPORTED_ABSENT = "reported_absent"
    UNKNOWN = "unknown"


class SourcedClaim(CoreModel):
    id: Text
    category: EvidenceCategory
    statement: Text
    attribution: ClaimAttribution = ClaimAttribution.UNKNOWN
    presence: ClaimPresence = ClaimPresence.REPORTED_PRESENT
    citations: Annotated[list[Citation], Field(min_length=1)]
    # Repeated descriptions retain provenance but do not become new achievements.
    duplicate_of: str | None


class AcademicRecord(CoreModel):
    claim_id: Text = Field(description="ID of an existing education claim in claims")
    institution: str | None
    qualification: str | None
    grade: str | None = Field(
        description="Original grade only: for GPA 8.2/10 use 8.2; never convert"
    )
    grade_scale: str | None = Field(
        description="Explicit grading maximum/system: for GPA 8.2/10 use 10"
    )
    # No conversion, prestige adjustment, or selection of a "best" GPA.


class Judgment(CoreModel):
    id: Text
    claim_id: Text
    dimension: Text
    label: Text
    rationale: Text
    citations: Annotated[list[Citation], Field(min_length=1)]


class CompetencySuggestion(CoreModel):
    id: Text
    claim_id: Text
    competency_id: str | None
    observed_skill: Text
    rationale: Text
    citations: Annotated[list[Citation], Field(min_length=1)]


class ContextKind(StrEnum):
    TOOL = "tool"
    DOMAIN = "domain"
    CONCEPT = "concept"


class RecognizedContext(CoreModel):
    """Cited terminology only; never a demonstrated skill or scoring input."""

    id: Text
    claim_id: Text
    kind: ContextKind
    label: Text
    rationale: Text
    citations: Annotated[list[Citation], Field(min_length=1)]


class Clarification(CoreModel):
    claim_id: str | None
    question: Text
    reason: Text


class UnderstandingDraft(CoreModel):
    claims: list[SourcedClaim]
    academics: list[AcademicRecord]
    judgments: list[Judgment]
    competencies: list[CompetencySuggestion]
    contexts: list[RecognizedContext] = Field(default_factory=list)
    questions: list[Clarification]
    unassessed: list[str]


class SupportVerdict(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"


class SupportCheck(CoreModel):
    target_id: Text
    verdict: SupportVerdict
    explanation: Text


class DuplicateGroup(CoreModel):
    canonical_claim_id: Text
    duplicate_claim_ids: Annotated[list[Text], Field(min_length=1)]
    explanation: Text


class SupportReview(CoreModel):
    checks: list[SupportCheck]
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)


class RubricDimension(CoreModel):
    id: Text
    description: Text
    labels: dict[str, str]


class EvaluationRubric(CoreModel):
    version: Text
    provisional: Literal[True]
    validated_by: None
    source: None
    dimensions: list[RubricDimension]
    category_guidance: dict[EvidenceCategory, str]

    @model_validator(mode="after")
    def validate_dimensions(self) -> EvaluationRubric:
        ids = [dimension.id for dimension in self.dimensions]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Rubric dimensions must be nonempty and unique")
        if any("unknown" not in dimension.labels for dimension in self.dimensions):
            raise ValueError("Every dimension must support unknown")
        if set(self.category_guidance) != set(EvidenceCategory):
            raise ValueError("Every evidence category needs rubric guidance")
        return self


class UnderstandingAudit(CoreModel):
    provider: Text
    model: Text
    completion_models: list[str]
    response_ids: list[str]
    prompt_version: Text
    prompt_sha256: Text
    rubric_sha256: Text
    rubric_snapshot: EvaluationRubric
    taxonomy_version: Text
    competency_catalog: dict[str, str]
    source_sha256: dict[str, str]
    draft_response_sha256: Text
    review_response_sha256: Text | None


class UnderstandingResult(CoreModel):
    response_version: Literal["understanding-v2", "understanding-v3"] = (
        "understanding-v2"
    )
    requires_confirmation: Literal[True] = True
    scoring_enabled: Literal[False] = False
    # Full sources make the interpretation reviewable, even when a file changes.
    documents: list[SourceDocument]
    draft: UnderstandingDraft
    support_review: SupportReview
    supported_claim_ids: list[str]
    supported_judgment_ids: list[str]
    supported_competency_ids: list[str]
    supported_context_ids: list[str] = Field(default_factory=list)
    questions: list[Clarification]
    limitations: list[str]
    audit: UnderstandingAudit

    @model_validator(mode="after")
    def validate_version(self) -> UnderstandingResult:
        if self.response_version == "understanding-v3":
            require_explicit_presence(self.draft)
        if self.response_version == "understanding-v2" and (
            self.draft.contexts
            or self.supported_context_ids
            or any(
                claim.presence != ClaimPresence.REPORTED_PRESENT
                for claim in self.draft.claims
            )
        ):
            raise ValueError("Typed presence and context require understanding-v3")
        return self


def require_explicit_presence(draft: UnderstandingDraft) -> None:
    """Legacy defaults are for old receipts, never omissions in new model output."""
    if any("presence" not in claim.model_fields_set for claim in draft.claims):
        raise ValueError("New interpretations must explicitly state claim presence")


def fingerprint(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def load_evaluation_rubric() -> EvaluationRubric:
    path: Path = DATA_ROOT / "taxonomy" / "evaluation_rubric.yaml"
    return EvaluationRubric.model_validate(yaml.safe_load(path.read_text("utf-8")))


def complete_unknown_dimensions(
    draft: UnderstandingDraft, rubric: EvaluationRubric
) -> UnderstandingDraft:
    """Expose omitted dimensions as unknown; never infer a positive judgment.

    This normalization is recorded in the rationale and reviewed like all other
    judgments. A small model need not repeat every unknown field perfectly.
    """
    pairs = {(item.claim_id, item.dimension) for item in draft.judgments}
    ids = (
        {item.id for item in draft.claims}
        | {item.id for item in draft.judgments}
        | {item.id for item in draft.competencies}
        | {item.id for item in draft.contexts}
    )
    judgments = list(draft.judgments)
    for claim in draft.claims:
        if claim.duplicate_of is not None:
            continue
        for dimension in rubric.dimensions:
            if (claim.id, dimension.id) in pairs:
                continue
            identifier = f"unassessed_{claim.id}_{dimension.id}"
            while identifier in ids:
                identifier += "_"
            ids.add(identifier)
            judgments.append(
                Judgment(
                    id=identifier,
                    claim_id=claim.id,
                    dimension=dimension.id,
                    label="unknown",
                    rationale="The model did not assess this dimension.",
                    citations=claim.citations,
                )
            )
    academics = list(draft.academics)
    recorded_ids = {record.claim_id for record in academics}
    questions = list(draft.questions)
    for claim in draft.claims:
        if (
            claim.category == EvidenceCategory.EDUCATION
            and claim.duplicate_of is None
            and claim.id not in recorded_ids
        ):
            academics.append(
                AcademicRecord(
                    claim_id=claim.id,
                    institution=None,
                    qualification=None,
                    grade=None,
                    grade_scale=None,
                )
            )
            questions.append(
                Clarification(
                    claim_id=claim.id,
                    question="Which school, qualification and grading scale apply?",
                    reason="The model did not extract an academic record here.",
                )
            )
    return draft.model_copy(
        update={
            "judgments": judgments,
            "academics": academics,
            "questions": questions,
        }
    )


def validate_draft(
    draft: UnderstandingDraft,
    documents: list[SourceDocument],
    rubric: EvaluationRubric,
    competency_catalog: dict[str, str],
) -> None:
    """Validate references and exact provenance, not semantic truth."""
    sources = {document.id: document.text for document in documents}
    if len(sources) != len(documents) or not sources:
        raise ValueError("Source document IDs must be unique and nonempty")
    claims = {claim.id: claim for claim in draft.claims}
    all_ids = (
        [item.id for item in draft.claims]
        + [item.id for item in draft.judgments]
        + [item.id for item in draft.competencies]
        + [item.id for item in draft.contexts]
    )
    if len(set(all_ids)) != len(all_ids):
        raise ValueError(
            "All claim, judgment, competency and context IDs must be unique"
        )

    def check_citations(citations: list[Citation]) -> None:
        for citation in citations:
            if not citation.quote.strip() or citation.quote not in sources.get(
                citation.document_id, ""
            ):
                raise ValueError("Citation must be an exact nonblank source passage")

    dimensions = {dimension.id: dimension for dimension in rubric.dimensions}
    pairs: set[tuple[str, str]] = set()
    for claim in draft.claims:
        check_citations(claim.citations)
        if claim.duplicate_of is not None:
            original = claims.get(claim.duplicate_of)
            if original is None or original.id == claim.id or original.duplicate_of:
                raise ValueError("Duplicate must point to a distinct canonical claim")
    linked_items: list[Judgment | CompetencySuggestion | RecognizedContext] = [
        *draft.judgments,
        *draft.competencies,
        *draft.contexts,
    ]
    for item in linked_items:
        if item.claim_id not in claims:
            raise ValueError("Unknown claim reference")
        # Keep duplicate-linked proposals reviewable. supported_ids excludes them
        # from credit, so a redundant model judgment cannot double-count the work.
        check_citations(item.citations)
    for judgment in draft.judgments:
        dimension = dimensions.get(judgment.dimension)
        if dimension is None or judgment.label not in dimension.labels:
            raise ValueError("Judgment uses an unknown rubric dimension or label")
        pair = (judgment.claim_id, judgment.dimension)
        if pair in pairs:
            raise ValueError("Only one judgment per claim and dimension is allowed")
        pairs.add(pair)
    for claim in draft.claims:
        if claim.duplicate_of is None and {
            dimension for claim_id, dimension in pairs if claim_id == claim.id
        } != set(dimensions):
            raise ValueError("Every canonical claim needs every rubric dimension")
    for suggestion in draft.competencies:
        if (
            suggestion.competency_id is not None
            and suggestion.competency_id not in competency_catalog
        ):
            raise ValueError(
                "Unknown competency ID; retain observed skill with null ID"
            )
    academic_ids = [record.claim_id for record in draft.academics]
    if len(set(academic_ids)) != len(academic_ids):
        raise ValueError("Duplicate academic record")
    if set(academic_ids) != {
        claim.id
        for claim in draft.claims
        if claim.category == EvidenceCategory.EDUCATION and claim.duplicate_of is None
    }:
        raise ValueError("Each canonical education claim needs its own academic record")
    for academic in draft.academics:
        if academic.claim_id not in claims:
            raise ValueError("Unknown academic claim")
        claim = claims[academic.claim_id]
        if claim.category != EvidenceCategory.EDUCATION or claim.duplicate_of:
            raise ValueError("Academic record must reference canonical education")
        passages = "\n".join(citation.quote for citation in claim.citations)
        for value in (
            academic.institution,
            academic.qualification,
            academic.grade,
            academic.grade_scale,
        ):
            if value is not None and (not value.strip() or value not in passages):
                raise ValueError("Academic values must preserve cited source wording")
    for question in draft.questions:
        if question.claim_id is not None and question.claim_id not in claims:
            raise ValueError("Question references unknown claim")


def supported_ids(
    draft: UnderstandingDraft, review: SupportReview
) -> tuple[list[str], list[str], list[str]]:
    """Fail closed on missing reviews; suppress children of rejected claims."""
    expected = (
        {item.id for item in draft.claims}
        | {item.id for item in draft.judgments}
        | {item.id for item in draft.competencies}
        | {item.id for item in draft.contexts}
    )
    actual = [check.target_id for check in review.checks]
    if len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError("Support review must cover each target exactly once")
    accepted = {
        check.target_id
        for check in review.checks
        if check.verdict == SupportVerdict.SUPPORTED
    }
    claim_map = {claim.id: claim for claim in draft.claims}
    grouped: set[str] = set()
    duplicate_ids: set[str] = set()
    for group in review.duplicate_groups:
        ids = [group.canonical_claim_id, *group.duplicate_claim_ids]
        if (
            len(set(ids)) != len(ids)
            or grouped.intersection(ids)
            or not set(ids).issubset(claim_map)
            or claim_map[group.canonical_claim_id].duplicate_of is not None
        ):
            raise ValueError("Duplicate groups must be disjoint valid claim references")
        grouped.update(ids)
        duplicate_ids.update(group.duplicate_claim_ids)
    claims = sorted(
        claim.id
        for claim in draft.claims
        if claim.id in accepted
        and claim.duplicate_of is None
        and claim.id not in duplicate_ids
    )
    judgments = sorted(
        item.id
        for item in draft.judgments
        if item.id in accepted
        and item.claim_id in claims
        and item.label != "unknown"
        and claim_map[item.claim_id].attribution == ClaimAttribution.STUDENT
        and claim_map[item.claim_id].presence == ClaimPresence.REPORTED_PRESENT
    )
    competencies = sorted(
        item.id
        for item in draft.competencies
        if item.id in accepted
        and item.claim_id in claims
        and claim_map[item.claim_id].attribution == ClaimAttribution.STUDENT
        and claim_map[item.claim_id].presence == ClaimPresence.REPORTED_PRESENT
    )
    return claims, judgments, competencies


def supported_context_ids(
    draft: UnderstandingDraft, review: SupportReview
) -> list[str]:
    """Retain reviewed context, including team context, without granting credit."""
    claims, _, _ = supported_ids(draft, review)
    accepted = {
        check.target_id
        for check in review.checks
        if check.verdict == SupportVerdict.SUPPORTED
    }
    return sorted(
        item.id
        for item in draft.contexts
        if item.id in accepted and item.claim_id in claims
    )


def canonical_json(value: CoreModel) -> str:
    data = value.model_dump(mode="json")
    if (
        isinstance(value, UnderstandingResult)
        and value.response_version == "understanding-v2"
    ):
        # Preserve historical receipt fingerprints when reading older results.
        data.pop("supported_context_ids", None)
        data["draft"].pop("contexts", None)
        for claim in data["draft"]["claims"]:
            claim.pop("presence", None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False)
