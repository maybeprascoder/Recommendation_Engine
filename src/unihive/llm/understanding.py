"""Generic interpretation followed by a separate semantic support review."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import JsonValue, ValidationError

from unihive.llm.provider import ProviderError, StructuredClient
from unihive.understanding import (
    ClaimPresence,
    Clarification,
    EvidenceCategory,
    SourceDocument,
    SupportReview,
    SupportVerdict,
    UnderstandingAudit,
    UnderstandingDraft,
    UnderstandingResult,
    canonical_json,
    complete_unknown_dimensions,
    fingerprint,
    load_evaluation_rubric,
    require_explicit_presence,
    supported_context_ids,
    supported_ids,
    validate_draft,
)

PROMPTS = Path(__file__).parent / "prompts"


def analyze_documents(
    documents: list[SourceDocument],
    client: StructuredClient,
    *,
    taxonomy_version: str,
    competency_catalog: dict[str, str],
) -> UnderstandingResult:
    """Implements Build Spec 5.1 with proposed labels and bounded model calls.

    A second pass tests semantic support but cannot establish external truth.
    No automatic retries, browsing, or scoring. At most two billable calls.
    """
    if not documents or len({doc.id for doc in documents}) != len(documents):
        raise ValueError("Provide documents with distinct IDs")
    if any(not document.text.strip() for document in documents):
        raise ValueError("Documents must contain readable text")
    if sum(len(document.text) for document in documents) > 100_000:
        raise ValueError("Input exceeds 100,000 characters; split documents explicitly")
    rubric = load_evaluation_rubric()
    instructions = (PROMPTS / "understanding_v1.txt").read_text("utf-8")
    review_instructions = (PROMPTS / "support_review_v1.txt").read_text("utf-8")
    payload: dict[str, JsonValue] = {
        "documents": [doc.model_dump(mode="json") for doc in documents],
        "rubric": rubric.model_dump(mode="json"),
        "allowed_competencies": dict(competency_catalog),
    }
    first = client.complete(
        instructions=instructions,
        payload=json.dumps(payload, ensure_ascii=False),
        schema=UnderstandingDraft.model_json_schema(),
        name="student_understanding",
    )
    try:
        draft = UnderstandingDraft.model_validate_json(first.text, strict=True)
        require_explicit_presence(draft)
        draft = complete_unknown_dimensions(draft, rubric)
        validate_draft(draft, documents, rubric, competency_catalog)
    except ValidationError as exc:
        # Pydantic errors can contain source text. Do not leak that into logs.
        raise ProviderError(
            "Interpretation failed schema or provenance validation"
        ) from exc
    except ValueError as exc:
        raise ProviderError(f"Interpretation rejected: {exc}") from exc
    payload["draft"] = draft.model_dump(mode="json")
    payload["required_review_target_ids"] = (
        [item.id for item in draft.claims]
        + [item.id for item in draft.judgments]
        + [item.id for item in draft.competencies]
        + [item.id for item in draft.contexts]
    )
    second = None
    if payload["required_review_target_ids"]:
        second = client.complete(
            instructions=review_instructions,
            payload=json.dumps(payload, ensure_ascii=False),
            schema=SupportReview.model_json_schema(),
            name="support_review",
        )
    try:
        review = (
            SupportReview.model_validate_json(second.text, strict=True)
            if second is not None
            else SupportReview(checks=[])
        )
        claim_ids, judgment_ids, competency_ids = supported_ids(draft, review)
    except (ValidationError, ValueError) as exc:
        raise ProviderError(
            "Support review failed validation or target coverage"
        ) from exc
    target_claims = {claim.id: claim.id for claim in draft.claims}
    target_claims.update({item.id: item.claim_id for item in draft.judgments})
    target_claims.update({item.id: item.claim_id for item in draft.competencies})
    target_claims.update({item.id: item.claim_id for item in draft.contexts})
    questions = list(draft.questions)
    if not draft.claims and not questions:
        questions.append(
            Clarification(
                claim_id=None,
                question="Describe one project, course, activity or work contribution.",
                reason="No assessable accomplishments were extracted.",
            )
        )
    for check in review.checks:
        if check.verdict != SupportVerdict.SUPPORTED:
            questions.append(
                Clarification(
                    claim_id=target_claims[check.target_id],
                    question="Can you clarify the source and your contribution?",
                    reason=check.explanation,
                )
            )
    for claim in draft.claims:
        if (
            claim.duplicate_of is None
            and claim.presence != ClaimPresence.REPORTED_ABSENT
            and claim.category
            in {
                EvidenceCategory.PROJECT,
                EvidenceCategory.WORK,
                EvidenceCategory.RESEARCH,
                EvidenceCategory.PUBLICATION,
                EvidenceCategory.COURSEWORK,
                EvidenceCategory.ACTIVITY,
                EvidenceCategory.OTHER,
            }
            and not any(item.claim_id == claim.id for item in questions)
            and not any(
                item.claim_id == claim.id
                and item.dimension == "depth"
                and item.id in judgment_ids
                for item in draft.judgments
            )
        ):
            questions.append(
                Clarification(
                    claim_id=claim.id,
                    question="What did you personally do, what methods did you use, "
                    "and how did you evaluate the result?",
                    reason="The source does not establish supported depth of work.",
                )
            )
    return UnderstandingResult(
        response_version="understanding-v3",
        documents=documents,
        draft=draft,
        support_review=review,
        supported_claim_ids=claim_ids,
        supported_judgment_ids=judgment_ids,
        supported_competency_ids=competency_ids,
        supported_context_ids=supported_context_ids(draft, review),
        questions=questions,
        limitations=[
            "Provisional qualitative rubric; the LLM supplies no numeric scores.",
            "Model support review is not independent verification of achievements.",
            "Institutions and venues have not been researched in this stage.",
            "Student confirmation is required before configured mappings apply.",
        ],
        audit=UnderstandingAudit(
            provider=client.provider,
            model=client.model,
            completion_models=[first.model] + ([second.model] if second else []),
            response_ids=[first.response_id] + ([second.response_id] if second else []),
            prompt_version="understanding-v9+support-review-v9",
            prompt_sha256=fingerprint(instructions + "\n" + review_instructions),
            rubric_sha256=fingerprint(canonical_json(rubric)),
            rubric_snapshot=rubric,
            taxonomy_version=taxonomy_version,
            competency_catalog=competency_catalog,
            source_sha256={doc.id: fingerprint(doc.text) for doc in documents},
            draft_response_sha256=fingerprint(first.text),
            review_response_sha256=fingerprint(second.text) if second else None,
        ),
    )
