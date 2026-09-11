"""Generic evidence contracts, semantic review filtering, and real CLI smoke."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from unihive.llm.analysis_cli import RecordedClient, RecordedResponses
from unihive.llm.provider import ProviderError
from unihive.llm.understanding import analyze_documents
from unihive.understanding import (
    SourceDocument,
    SupportReview,
    UnderstandingDraft,
    complete_unknown_dimensions,
    load_evaluation_rubric,
    supported_ids,
    validate_draft,
)

TEXT = (
    "I designed a rainwater monitor and compared sensor readings "
    "against a manual gauge."
)
ROOT = Path(__file__).resolve().parents[1]


def example() -> dict:
    citation = {"document_id": "document-1", "quote": TEXT}
    return {
        "claims": [
            {
                "id": "c1",
                "category": "project",
                "statement": TEXT,
                "attribution": "student",
                "citations": [citation],
                "duplicate_of": None,
            }
        ],
        "academics": [],
        "judgments": [
            {
                "id": "j" + str(i),
                "claim_id": "c1",
                "dimension": dimension,
                "label": label,
                "rationale": "The passage describes the work.",
                "citations": [citation],
            }
            for i, (dimension, label) in enumerate(
                [
                    ("ownership", "unknown"),
                    ("depth", "designed"),
                    ("evaluation", "compared"),
                    ("impact", "unknown"),
                ]
            )
        ],
        "competencies": [
            {
                "id": "s1",
                "claim_id": "c1",
                "competency_id": None,
                "observed_skill": "sensor evaluation",
                "rationale": "Explicit comparison with a reference gauge.",
                "citations": [citation],
            }
        ],
        "questions": [],
        "unassessed": ["Ownership and adoption are not established."],
    }


def review_for(draft: dict) -> dict:
    return {
        "checks": [
            {
                "target_id": item["id"],
                "verdict": "supported",
                "explanation": "Consistent with the supplied passage.",
            }
            for key in ("claims", "judgments", "competencies")
            for item in draft[key]
        ]
    }


def parse(data: dict) -> UnderstandingDraft:
    return UnderstandingDraft.model_validate_json(json.dumps(data), strict=True)


def validate(data: dict) -> None:
    validate_draft(
        parse(data),
        [SourceDocument(id="document-1", text=TEXT)],
        load_evaluation_rubric(),
        {"programming": "Writing software"},
    )


def test_unfamiliar_project_is_preserved_without_invented_taxonomy() -> None:
    data = example()
    validate(data)
    responses = RecordedResponses(
        draft=parse(data), review=SupportReview(**review_for(data))
    )
    result = analyze_documents(
        [SourceDocument(id="document-1", text=TEXT)],
        RecordedClient(responses),
        taxonomy_version="test-v1",
        competency_catalog={},
    )
    assert result.supported_claim_ids == ["c1"]
    assert result.supported_judgment_ids == ["j1", "j2"]
    assert result.supported_competency_ids == ["s1"]
    assert not result.scoring_enabled and result.requires_confirmation
    assert result.audit.provider == "recorded-offline"
    assert result.audit.rubric_snapshot.provisional


@pytest.mark.parametrize(
    "mutation",
    [
        "quote",
        "blank_quote",
        "source",
        "competency",
        "label",
        "dimension",
        "missing_dimension",
        "duplicate_id",
        "duplicate_dimension",
        "claim_reference",
        "self_duplicate",
        "unknown_duplicate",
        "question_reference",
    ],
)
def test_invalid_provenance_and_references_fail_closed(mutation: str) -> None:
    data = example()
    if mutation == "quote":
        data["claims"][0]["citations"][0]["quote"] = (
            "I published a top conference paper."
        )
    elif mutation == "blank_quote":
        data["claims"][0]["citations"][0]["quote"] = " "
    elif mutation == "source":
        data["claims"][0]["citations"][0]["document_id"] = "nonexistent"
    elif mutation == "competency":
        data["competencies"][0]["competency_id"] = "invented"
    elif mutation == "label":
        data["judgments"][0]["label"] = "world_class"
    elif mutation == "dimension":
        data["judgments"][0]["dimension"] = "prestige"
    elif mutation == "missing_dimension":
        data["judgments"].pop()
    elif mutation == "duplicate_id":
        data["judgments"][0]["id"] = "c1"
    elif mutation == "duplicate_dimension":
        data["judgments"][0]["dimension"] = "depth"
    elif mutation == "claim_reference":
        data["judgments"][0]["claim_id"] = "invented"
    elif mutation == "self_duplicate":
        data["claims"][0]["duplicate_of"] = "c1"
    elif mutation == "unknown_duplicate":
        data["claims"][0]["duplicate_of"] = "missing"
    elif mutation == "question_reference":
        data["questions"] = [
            {"claim_id": "missing", "question": "Explain?", "reason": "Missing"}
        ]
    with pytest.raises(ValueError):
        validate(data)


def test_rejected_claim_suppresses_even_accepted_child_judgments() -> None:
    data = example()
    checks = review_for(data)
    checks["checks"][0]["verdict"] = "unsupported"
    checks["checks"][0]["explanation"] = (
        "Source describes coursework, not a publication."
    )
    assert supported_ids(parse(data), SupportReview(**checks)) == ([], [], [])


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "invented"])
def test_review_requires_exact_target_coverage(mutation: str) -> None:
    data = example()
    checks = review_for(data)
    if mutation == "missing":
        checks["checks"].pop()
    elif mutation == "duplicate":
        checks["checks"].append(checks["checks"][0])
    else:
        checks["checks"][0]["target_id"] = "invented"
    with pytest.raises(ValueError, match="exactly once"):
        supported_ids(parse(data), SupportReview(**checks))


def test_semantic_rejection_generates_clarification() -> None:
    data = example()
    checks = review_for(data)
    checks["checks"][2]["verdict"] = "uncertain"
    client = RecordedClient(
        RecordedResponses(draft=parse(data), review=SupportReview(**checks))
    )
    result = analyze_documents(
        [SourceDocument(id="document-1", text=TEXT)],
        client,
        taxonomy_version="test",
        competency_catalog={},
    )
    assert "j1" not in result.supported_judgment_ids
    assert result.questions[0].claim_id == "c1"


def test_invalid_draft_does_not_make_review_call() -> None:
    data = example()
    data["claims"][0]["citations"][0]["quote"] = "invented quote"
    client = RecordedClient(
        RecordedResponses(draft=parse(data), review=SupportReview(checks=[]))
    )
    with pytest.raises(ProviderError, match="source passage"):
        analyze_documents(
            [SourceDocument(id="document-1", text=TEXT)],
            client,
            taxonomy_version="test",
            competency_catalog={},
        )
    assert next(client._responses).checks == []


def test_real_cli_offline_and_no_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "student.txt"
    source.write_text(TEXT, encoding="utf-8")
    recorded = tmp_path / "responses.json"
    data = example()
    recorded.write_text(
        json.dumps({"draft": data, "review": review_for(data)}), encoding="utf-8"
    )
    output = tmp_path / "result.json"
    executable = Path(sys.executable).with_name(
        "unihive.exe" if os.name == "nt" else "unihive"
    )
    command = [
        str(executable),
        "analyze",
        "--input",
        str(source),
        "--recorded-responses",
        str(recorded),
        "--output",
        str(output),
    ]
    first = subprocess.run(
        command, capture_output=True, text=True, timeout=30, cwd=tmp_path
    )
    assert first.returncode == 0, first.stderr
    result = json.loads(output.read_text("utf-8"))
    assert result["supported_judgment_ids"] == ["j1", "j2"]
    assert result["audit"]["provider"] == "recorded-offline"
    second = subprocess.run(
        command, capture_output=True, text=True, timeout=30, cwd=tmp_path
    )
    assert second.returncode == 2
    assert "already exists" in second.stderr
    assert source.read_text("utf-8") == TEXT


def test_multiple_grading_scales_preserved_and_conversion_rejected() -> None:
    data = example()
    first = "Example College, BSc, GPA 8.2/10."
    second = "Sample Institute, MSc, GPA 3.6/4.0."
    data["claims"] = []
    data["judgments"] = []
    data["competencies"] = []
    for index, text in enumerate([first, second]):
        claim_id = f"a{index}"
        citations = [{"document_id": "document-1", "quote": text}]
        data["claims"].append(
            {
                "id": claim_id,
                "category": "education",
                "statement": text,
                "citations": citations,
                "duplicate_of": None,
            }
        )
        for dimension in load_evaluation_rubric().dimensions:
            data["judgments"].append(
                {
                    "id": claim_id + dimension.id,
                    "claim_id": claim_id,
                    "dimension": dimension.id,
                    "label": "unknown",
                    "rationale": "Degree alone does not establish work quality.",
                    "citations": citations,
                }
            )
    data["academics"] = [
        {
            "claim_id": "a0",
            "institution": "Example College",
            "qualification": "BSc",
            "grade": "8.2",
            "grade_scale": "10",
        },
        {
            "claim_id": "a1",
            "institution": "Sample Institute",
            "qualification": "MSc",
            "grade": "3.6",
            "grade_scale": "4.0",
        },
    ]
    documents = [SourceDocument(id="document-1", text=first + "\n" + second)]
    validate_draft(parse(data), documents, load_evaluation_rubric(), {})
    data["academics"][0]["grade"] = "3.28"
    with pytest.raises(ValueError, match="preserve"):
        validate_draft(parse(data), documents, load_evaluation_rubric(), {})


def test_duplicate_description_retains_source_without_extra_judgments() -> None:
    data = example()
    duplicate = dict(data["claims"][0], id="c2", duplicate_of="c1")
    data["claims"].append(duplicate)
    validate(data)
    claims, judgments, _ = supported_ids(parse(data), SupportReview(**review_for(data)))
    assert claims == ["c1"]
    assert judgments == ["j1", "j2"]
    data["judgments"].append(dict(data["judgments"][1], id="j_dup", claim_id="c2"))
    validate(data)
    assert (
        "j_dup" not in supported_ids(parse(data), SupportReview(**review_for(data)))[1]
    )


def test_missing_dimensions_become_explicit_unknown_never_positive():
    data = example()
    data["judgments"] = []
    draft = complete_unknown_dimensions(parse(data), load_evaluation_rubric())
    assert len(draft.judgments) == 4
    assert {item.label for item in draft.judgments} == {"unknown"}
    validate_draft(
        draft,
        [SourceDocument(id="document-1", text=TEXT)],
        load_evaluation_rubric(),
        {},
    )
    reviewed = review_for(draft.model_dump(mode="json"))
    assert supported_ids(draft, SupportReview(**reviewed))[1] == []


def test_empty_interpretation_skips_review_and_asks_for_evidence():
    data = {key: [] for key in example()}
    data["unassessed"] = ["Skills are listed without supporting activities."]
    client = RecordedClient(
        RecordedResponses(
            draft=parse(data),
            review=SupportReview(checks=[]),
        )
    )
    result = analyze_documents(
        [SourceDocument(id="document-1", text="Skills: Python, leadership")],
        client,
        taxonomy_version="test",
        competency_catalog={},
    )
    assert result.supported_claim_ids == []
    assert len(result.audit.response_ids) == 1
    assert result.audit.review_response_sha256 is None
    assert result.questions[0].claim_id is None
    assert next(client._responses).checks == []  # No unnecessary review call.


def test_incomplete_education_gets_unknown_record_and_clarification():
    data = example()
    data["claims"][0]["category"] = "education"
    draft = complete_unknown_dimensions(parse(data), load_evaluation_rubric())
    validate_draft(
        draft,
        [SourceDocument(id="document-1", text=TEXT)],
        load_evaluation_rubric(),
        {},
    )
    academic = draft.academics[0]
    assert academic.claim_id == "c1"
    assert academic.grade is None and academic.grade_scale is None
    assert academic.qualification is None and academic.institution is None
    assert "did not extract" in draft.questions[0].reason


@pytest.mark.parametrize("attribution", ["other", "team", "unknown"])
def test_other_peoples_work_cannot_grant_student_judgments(attribution):
    data = example()
    data["claims"][0]["attribution"] = attribution
    claims, judgments, competencies = supported_ids(
        parse(data),
        SupportReview(**review_for(data)),
    )
    assert claims == ["c1"]  # Context is preserved, not credited to the student.
    assert judgments == [] and competencies == []


def test_reviewer_detected_duplicates_are_not_counted_twice():
    data = example()
    data["claims"].append(dict(data["claims"][0], id="c2"))
    for item in list(data["judgments"]):
        data["judgments"].append(dict(item, id=item["id"] + "b", claim_id="c2"))
    review = review_for(data)
    review["duplicate_groups"] = [
        {
            "canonical_claim_id": "c1",
            "duplicate_claim_ids": ["c2"],
            "explanation": "Same deliverable repeated under internship.",
        }
    ]
    claims, judgments, _ = supported_ids(parse(data), SupportReview(**review))
    assert claims == ["c1"]
    assert judgments == ["j1", "j2"]


@pytest.mark.parametrize("duplicates", [["c1"], ["missing"], ["c2", "c2"]])
def test_invalid_duplicate_groups_are_rejected(duplicates):
    data = example()
    data["claims"].append(dict(data["claims"][0], id="c2"))
    review = review_for(data)
    review["duplicate_groups"] = [
        {
            "canonical_claim_id": "c1",
            "duplicate_claim_ids": duplicates,
            "explanation": "Invalid group",
        }
    ]
    with pytest.raises(ValueError, match="Duplicate groups"):
        supported_ids(parse(data), SupportReview(**review))
