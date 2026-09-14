"""Recorded boundary checks; these do not measure live model semantic accuracy."""

import json
from datetime import date

import pytest
from pydantic import ValidationError
from test_understanding_review import confirm_result, empty_profile
from understanding_samples import qualitative_result

from unihive.competency import resolve_competencies
from unihive.llm.analysis_cli import RecordedClient, RecordedResponses
from unihive.llm.provider import Completion, ProviderError
from unihive.llm.understanding import analyze_documents
from unihive.models import EvidenceState
from unihive.taxonomy import load_taxonomy
from unihive.understanding import (
    ClaimPresence,
    SourceDocument,
    SupportReview,
    UnderstandingDraft,
    UnderstandingResult,
    canonical_json,
    complete_unknown_dimensions,
    fingerprint,
    load_evaluation_rubric,
    supported_context_ids,
    supported_ids,
    validate_draft,
)
from unihive.understanding_review import (
    ClaimDecision,
    initial_claim_corrections,
    validate_understanding,
)


def recorded(text="I have no publications.", presence="reported_absent", tool=None):
    citation = {"document_id": "resume", "quote": text}
    draft = complete_unknown_dimensions(
        UnderstandingDraft.model_validate(
            {
                "claims": [
                    {
                        "id": "c1",
                        "category": "publication",
                        "statement": text,
                        "attribution": "student",
                        "presence": presence,
                        "citations": [citation],
                        "duplicate_of": None,
                    }
                ],
                "academics": [],
                "judgments": [],
                "competencies": [],
                "contexts": (
                    [
                        {
                            "id": "t1",
                            "claim_id": "c1",
                            "kind": "tool",
                            "label": tool,
                            "rationale": "A named tool only.",
                            "citations": [citation],
                        }
                    ]
                    if tool
                    else []
                ),
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
                    "verdict": "supported",
                    "explanation": "Recorded.",
                }
                for item in [*draft.claims, *draft.judgments, *draft.contexts]
            ]
        }
    )
    return draft, review


def analyze(draft, review):
    taxonomy = load_taxonomy()
    return analyze_documents(
        [
            SourceDocument(
                id="resume",
                text="\n".join(
                    c.quote for claim in draft.claims for c in claim.citations
                ),
            )
        ],
        RecordedClient(RecordedResponses(draft=draft, review=review)),
        taxonomy_version=taxonomy.understanding_version,
        competency_catalog={n.id: n.description for n in taxonomy.competencies},
    )


def test_confirmed_absence_retains_scope_and_does_not_create_competency_absence():
    result = analyze(*recorded())
    assert result.response_version == "understanding-v3"
    assert not result.questions  # No request to describe work explicitly denied.
    profile = confirm_result(empty_profile(), result)
    assert len(profile.evidence) == 1
    item = profile.evidence[0]
    assert item.state == EvidenceState.CONFIRMED_ABSENT
    assert item.raw_text == "I have no publications."
    assert item.source_claim_id == "c1" and item.source_interpretation_sha256
    assert item.scoring_exclusion and not item.qualitative_mapping
    assert confirm_result(profile, result) == profile
    resolved = resolve_competencies(profile, load_taxonomy(), as_of=date(2026, 1, 1))
    assert all(c.state == EvidenceState.UNKNOWN for c in resolved)


@pytest.mark.parametrize("presence", ["reported_absent", "unknown"])
def test_non_present_claim_cannot_supply_positive_mappings_even_if_review_accepts(
    presence,
):
    result = qualitative_result(
        text="I have no publications.",
        category="publication",
        labels={"depth": "designed", "evaluation": "compared", "impact": "measured"},
        skills={"ML": "machine_learning"},
    )
    draft = result.draft.model_copy(
        update={
            "claims": [
                result.draft.claims[0].model_copy(
                    update={"presence": ClaimPresence(presence)}
                )
            ]
        }
    )
    result = analyze(draft, result.support_review)
    assert not result.supported_judgment_ids and not result.supported_competency_ids
    changes = [
        c.model_copy(update={"decision": ClaimDecision.CONFIRM})
        for c in initial_claim_corrections(result)
    ]
    profile = confirm_result(empty_profile(), result, changes)
    assert len(profile.evidence) == 1 and not profile.evidence[0].qualitative_mapping
    assert profile.evidence[0].state == (
        EvidenceState.CONFIRMED_ABSENT
        if presence == "reported_absent"
        else EvidenceState.UNKNOWN
    )


@pytest.mark.parametrize("verdict", ["unsupported", "uncertain"])
def test_student_confirmation_cannot_override_rejected_absence(verdict):
    draft, review = recorded()
    review = review.model_copy(
        update={
            "checks": [
                c.model_copy(update={"verdict": verdict}) if c.target_id == "c1" else c
                for c in review.checks
            ]
        }
    )
    result = analyze(draft, review)
    changes = [
        c.model_copy(update={"decision": ClaimDecision.CONFIRM})
        for c in initial_claim_corrections(result)
    ]
    assert not confirm_result(empty_profile(), result, changes).evidence


@pytest.mark.parametrize("presence", ["reported_present", "reported_absent", "unknown"])
def test_changing_presence_requires_another_support_review(presence):
    result = analyze(*recorded(presence=presence))
    changes = [
        c.model_copy(
            update={
                "presence": (
                    ClaimPresence.REPORTED_ABSENT
                    if presence == "reported_present"
                    else ClaimPresence.REPORTED_PRESENT
                ),
                "decision": ClaimDecision.CONFIRM,
            }
        )
        for c in initial_claim_corrections(result)
    ]
    assert not confirm_result(empty_profile(), result, changes).evidence


@pytest.mark.parametrize(
    "tool",
    [
        "ETABS",
        "AutoCAD",
        "ANSYS",
        "SolidWorks",
        "MATLAB",
        "Arduino",
        "Verilog",
        "Wireshark",
        "Nessus",
        "Kali Linux",
        "TensorFlow",
        "PyTorch",
        "React",
        "SQL",
    ],
)
def test_tool_context_is_reviewed_and_retained_without_skill_credit(tool):
    result = analyze(*recorded(f"Used {tool}.", "reported_present", tool))
    assert result.supported_context_ids == ["t1"]
    assert not result.supported_competency_ids and not result.supported_judgment_ids
    assert result.questions
    restored = UnderstandingResult.model_validate_json(result.model_dump_json())
    assert restored.draft.contexts[0].label == tool
    profile = confirm_result(empty_profile(), restored)
    assert all(item.scoring_exclusion for item in profile.evidence)


@pytest.mark.parametrize(
    "mutation",
    ["missing_review", "duplicate_review", "bad_quote", "bad_parent", "duplicate_id"],
)
def test_context_provenance_and_review_coverage_fail_closed(mutation):
    draft, review = recorded("Used ETABS.", "reported_present", "ETABS")
    if mutation == "missing_review":
        review = review.model_copy(update={"checks": review.checks[:-1]})
    elif mutation == "duplicate_review":
        review = review.model_copy(
            update={"checks": [*review.checks, review.checks[-1]]}
        )
    else:
        item = draft.contexts[0]
        updates = (
            {"citations": [item.citations[0].model_copy(update={"quote": "Invented"})]}
            if mutation == "bad_quote"
            else {"claim_id": "missing"}
            if mutation == "bad_parent"
            else {"id": "c1"}
        )
        draft = draft.model_copy(update={"contexts": [item.model_copy(update=updates)]})
    with pytest.raises(ProviderError):
        analyze(draft, review)


def test_rejected_parent_and_rejected_context_cannot_appear_as_supported_context():
    draft, review = recorded("Used ETABS.", "reported_present", "ETABS")
    for target in ("c1", "t1"):
        changed = review.model_copy(
            update={
                "checks": [
                    c.model_copy(update={"verdict": "unsupported"})
                    if c.target_id == target
                    else c
                    for c in review.checks
                ]
            }
        )
        assert not supported_context_ids(draft, changed)
    result = analyze(draft, review)
    with pytest.raises(ValueError, match="context support"):
        validate_understanding(
            result.model_copy(update={"supported_context_ids": []}),
            result.audit.taxonomy_version,
        )


def test_unknown_completion_respects_context_id_namespace():
    draft, _ = recorded("Used ETABS.", "reported_present", "ETABS")
    draft = draft.model_copy(
        update={
            "judgments": [],
            "contexts": [
                draft.contexts[0].model_copy(update={"id": "unassessed_c1_depth"})
            ],
        }
    )
    draft = complete_unknown_dimensions(draft, load_evaluation_rubric())
    validate_draft(
        draft,
        [SourceDocument(id="resume", text="Used ETABS.")],
        load_evaluation_rubric(),
        {},
    )
    assert "unassessed_c1_depth_" in {j.id for j in draft.judgments}


def test_legacy_receipt_fingerprint_remains_stable_and_extensions_require_v3():
    result = qualitative_result(text="I built a project.")
    old = result.model_dump(mode="json")
    old["response_version"] = "understanding-v2"
    old.pop("supported_context_ids")
    old["draft"].pop("contexts")
    for claim in old["draft"]["claims"]:
        claim.pop("presence")
    expected = json.dumps(old, sort_keys=True, ensure_ascii=False)
    restored = UnderstandingResult.model_validate(old)
    assert canonical_json(restored) == expected
    first = confirm_result(empty_profile(), restored)
    assert all(
        e.source_interpretation_sha256 == fingerprint(expected) for e in first.evidence
    )
    assert (
        confirm_result(first, UnderstandingResult.model_validate_json(expected))
        == first
    )
    old["draft"]["claims"][0]["presence"] = "reported_absent"
    with pytest.raises(ValidationError, match="require understanding-v3"):
        UnderstandingResult.model_validate(old)


def test_positive_work_and_separate_absence_keep_independent_scopes():
    positive = qualitative_result(
        text="I wrote Python code to implement the classifier.",
        labels={"depth": "applied"},
        skills={"code": "programming"},
    )
    absent, absence_review = recorded()
    absent = absent.model_copy(
        update={
            "claims": [absent.claims[0].model_copy(update={"id": "absent"})],
            "judgments": [
                j.model_copy(update={"id": "absent-" + j.id, "claim_id": "absent"})
                for j in absent.judgments
            ],
        }
    )
    draft = positive.draft.model_copy(
        update={
            "claims": [*positive.draft.claims, *absent.claims],
            "judgments": [*positive.draft.judgments, *absent.judgments],
        }
    )
    review = positive.support_review.model_copy(
        update={
            "checks": [
                *positive.support_review.checks,
                *[
                    c.model_copy(
                        update={
                            "target_id": "absent"
                            if c.target_id == "c1"
                            else "absent-" + c.target_id
                        }
                    )
                    for c in absence_review.checks
                ],
            ]
        }
    )
    result = analyze(draft, review)
    assert supported_ids(draft, review)[2] == ["code"]
    profile = confirm_result(empty_profile(), result)
    assert any(
        e.qualitative_mapping for e in profile.evidence if e.source_claim_id == "c1"
    )
    assert all(
        e.state == EvidenceState.CONFIRMED_ABSENT and not e.qualitative_mapping
        for e in profile.evidence
        if e.source_claim_id == "absent"
    )


def test_new_model_output_cannot_use_legacy_present_default():
    draft, _ = recorded()
    raw = draft.model_dump(mode="json")
    del raw["claims"][0]["presence"]

    class MissingPresenceClient:
        provider = "recorded-offline"
        model = "recorded-offline"

        def complete(self, **kwargs):
            assert kwargs["name"] == "student_understanding"  # No second call.
            return Completion(
                text=json.dumps(raw), response_id="test", model=self.model
            )

    with pytest.raises(ProviderError, match="explicitly state claim presence"):
        analyze_documents(
            [SourceDocument(id="resume", text="I have no publications.")],
            MissingPresenceClient(),
            taxonomy_version="test",
            competency_catalog={},
        )
