"""Synthetic interpretation shared by adapter and live HTTP tests."""

from unihive.llm.analysis_cli import RecordedClient, RecordedResponses
from unihive.llm.understanding import analyze_documents
from unihive.taxonomy import load_taxonomy
from unihive.understanding import (
    SourceDocument,
    SupportReview,
    UnderstandingDraft,
    UnderstandingResult,
    complete_unknown_dimensions,
    load_evaluation_rubric,
)


def mixed_result() -> UnderstandingResult:
    passages = {
        "student": "I designed a sensor system — 学生.",
        "team": "Our team deployed the system.",
        "other": "My supervisor published the findings.",
        "unknown": "Won an award.",
        "duplicate": "I designed a sensor system — 学生.",
        "review-duplicate": "I designed a sensor system — 学生.",
        "unsupported": "A project was discussed.",
        "uncertain": "I may have helped with testing.",
        "education": "Example College, BSc, GPA 8.2/10.",
    }
    claims = [
        {
            "id": key,
            "category": "education" if key == "education" else "project",
            "statement": passage,
            "attribution": key if key in {"team", "other", "unknown"} else "student",
            "citations": [{"document_id": "resume", "quote": passage}],
            "duplicate_of": "student" if key == "duplicate" else None,
        }
        for key, passage in passages.items()
    ]
    draft = complete_unknown_dimensions(
        UnderstandingDraft.model_validate(
            {
                "claims": claims,
                "academics": [
                    {
                        "claim_id": "education",
                        "institution": "Example College",
                        "qualification": "BSc",
                        "grade": "8.2",
                        "grade_scale": "10",
                    }
                ],
                "judgments": [
                    {
                        "id": "depth-student",
                        "claim_id": "student",
                        "dimension": "depth",
                        "label": "designed",
                        "rationale": "The source describes design.",
                        "citations": claims[0]["citations"],
                    }
                ],
                "competencies": [],
                "questions": [],
                "unassessed": ["Venue quality"],
            }
        ),
        load_evaluation_rubric(),
    )
    review = SupportReview.model_validate(
        {
            "checks": [
                {
                    "target_id": item.id,
                    "verdict": item.id
                    if item.id in {"unsupported", "uncertain"}
                    else "supported",
                    "explanation": "Synthetic support check.",
                }
                for item in [*draft.claims, *draft.judgments]
            ],
            "duplicate_groups": [
                {
                    "canonical_claim_id": "student",
                    "duplicate_claim_ids": ["review-duplicate"],
                    "explanation": "Repeated project.",
                }
            ],
        }
    )
    return analyze_documents(
        [SourceDocument(id="resume", text="\n".join(passages.values()))],
        RecordedClient(RecordedResponses(draft=draft, review=review)),
        taxonomy_version=load_taxonomy().understanding_version,
        competency_catalog={},
    )


def qualitative_result(
    text: str,
    *,
    category: str = "project",
    labels: dict[str, str] | None = None,
    skills: dict[str, str | None] | None = None,
    rejected: tuple[str, ...] = (),
    attribution: str = "student",
) -> UnderstandingResult:
    """Mock both bounded LLM calls; run production schema and support filtering."""
    citation = {"document_id": "resume", "quote": text}
    draft = complete_unknown_dimensions(
        UnderstandingDraft.model_validate(
            {
                "claims": [
                    {
                        "id": "c1",
                        "category": category,
                        "statement": text,
                        "attribution": attribution,
                        "citations": [citation],
                        "duplicate_of": None,
                    }
                ],
                "academics": [],
                "judgments": [
                    {
                        "id": dimension,
                        "claim_id": "c1",
                        "dimension": dimension,
                        "label": label,
                        "rationale": "Mock source interpretation.",
                        "citations": [citation],
                    }
                    for dimension, label in (labels or {}).items()
                ],
                "competencies": [
                    {
                        "id": skill,
                        "claim_id": "c1",
                        "competency_id": competency,
                        "observed_skill": skill,
                        "rationale": "Mock source interpretation.",
                        "citations": [citation],
                    }
                    for skill, competency in (skills or {}).items()
                ],
                "questions": [],
                "unassessed": [],
            }
        ),
        load_evaluation_rubric(),
    )
    review = SupportReview.model_validate(
        {
            "checks": [
                {
                    "target_id": item.id,
                    "verdict": "unsupported" if item.id in rejected else "supported",
                    "explanation": "Source does not support this proposal."
                    if item.id in rejected
                    else "Consistent with the source.",
                }
                for item in [*draft.claims, *draft.judgments, *draft.competencies]
            ]
        }
    )
    taxonomy = load_taxonomy()
    return analyze_documents(
        [SourceDocument(id="resume", text=text)],
        RecordedClient(RecordedResponses(draft=draft, review=review)),
        taxonomy_version=taxonomy.understanding_version,
        competency_catalog={
            node.id: node.description for node in taxonomy.competencies
        },
    )
