"""Claim-scoped QA checks expose known failures without altering scoring."""

from pathlib import Path

import pytest

from qa.cross_domain_evidence import (
    compare,
    coverage_gaps,
    interpret,
    load_suite,
    project,
    training_records,
    validate_case,
)
from unihive.models import EvidenceState
from unihive.taxonomy import load_taxonomy
from unihive.understanding import ClaimPresence, CompetencySuggestion, EvidenceCategory

ROOT = Path(__file__).resolve().parents[1]
SUITE = load_suite(ROOT / "tests/fixtures/understanding/context_presence_golden.json")
CASES = {c.id: c for c in SUITE.cases}


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


@pytest.mark.parametrize("case", SUITE.cases, ids=CASES)
def test_v3_references_preserve_scope_and_provisional_status(case, taxonomy):
    assert SUITE.provisional and SUITE.validated_by is None
    assert (
        case.validated_by is None
        and case.annotation_status == "provisional_synthetic_reference"
    )
    validate_case(case, taxonomy)
    result = interpret(case, taxonomy)
    assert not compare(case, result)
    profile = project(result, taxonomy)
    if case.id == "context-mixed":
        assert [e.state for e in profile.evidence] == [
            EvidenceState.SELF_REPORTED_PRESENT,
            EvidenceState.CONFIRMED_ABSENT,
            EvidenceState.SELF_REPORTED_PRESENT,
        ]
    assert sum(e.qualitative_mapping is not None for e in profile.evidence) == (
        1 if case.id == "context-programming-project" else 0
    )
    exports = training_records(case)
    assert exports[0]["expected_output"]["contexts"]
    assert exports[0]["annotation_schema_version"] == "understanding-v3"
    assert all("presence" in c for c in exports[0]["expected_output"]["claims"])
    assert exports[0]["annotation_status"] == "provisional_synthetic_reference"


@pytest.mark.parametrize("case", SUITE.cases, ids=CASES)
def test_v3_review_challenges_cannot_confer_credit(case, taxonomy):
    result = interpret(case, taxonomy, challenge=True)
    supported = {
        *result.supported_claim_ids,
        *result.supported_judgment_ids,
        *result.supported_competency_ids,
        *result.supported_context_ids,
    }
    assert not supported.intersection(case.review_challenge.rejected_ids)
    assert not any(e.qualitative_mapping for e in project(result, taxonomy).evidence)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("presence", "claim[2]:presence:"),
        ("category", "claim[3]:unsupported_category:coursework"),
        ("context", "claim[1]:missing_context:tool:ETABS"),
        ("null_route", "claim[3]:false_negative_competency:programming"),
        ("tool_skill", "claim[1]:context_or_absence_promoted_to_skill"),
        ("wrong_parent", "claim[3]:false_negative_competency:programming"),
        ("labels", "claim[1]:label:depth:expected unknown, got applied"),
        ("alignment", "claim[1]:source_alignment:expected 1, got 2"),
    ],
)
def test_claim_oracle_catches_errors_hidden_by_document_level_totals(
    mutation, expected, taxonomy
):
    case = CASES["context-mixed"]
    result = interpret(case, taxonomy)
    draft = result.draft
    if mutation == "presence":
        claims = [
            c.model_copy(update={"presence": ClaimPresence.REPORTED_PRESENT})
            if c.id == "c2"
            else c
            for c in draft.claims
        ]
        draft = draft.model_copy(update={"claims": claims})
    elif mutation == "category":
        draft = draft.model_copy(
            update={
                "claims": [
                    c.model_copy(update={"category": EvidenceCategory.COURSEWORK})
                    if c.id == "c3"
                    else c
                    for c in draft.claims
                ]
            }
        )
    elif mutation == "context":
        result = result.model_copy(update={"supported_context_ids": ["t2"]})
    elif mutation == "null_route":
        draft = draft.model_copy(
            update={
                "competencies": [
                    draft.competencies[0].model_copy(update={"competency_id": None})
                ]
            }
        )
    elif mutation == "tool_skill":
        skill = CompetencySuggestion(
            id="bad",
            claim_id="c1",
            competency_id=None,
            observed_skill="ETABS usage",
            rationale="Named tool only.",
            citations=draft.claims[0].citations,
        )
        draft = draft.model_copy(update={"competencies": [*draft.competencies, skill]})
        result = result.model_copy(update={"supported_competency_ids": ["s1", "bad"]})
    elif mutation == "wrong_parent":
        draft = draft.model_copy(
            update={
                "competencies": [
                    draft.competencies[0].model_copy(update={"claim_id": "c1"})
                ]
            }
        )
    elif mutation == "labels":
        draft = draft.model_copy(
            update={
                "judgments": [
                    j.model_copy(update={"label": "applied"})
                    if j.id == "j1-depth"
                    else j.model_copy(update={"label": "unknown"})
                    if j.id == "j3-depth"
                    else j
                    for j in draft.judgments
                ]
            }
        )
        result = result.model_copy(update={"supported_judgment_ids": ["j1-depth"]})
    else:
        duplicate = draft.claims[0].model_copy(update={"id": "another"})
        draft = draft.model_copy(update={"claims": [*draft.claims, duplicate]})
        result = result.model_copy(
            update={"supported_claim_ids": [*result.supported_claim_ids, "another"]}
        )
    failures = compare(case, result.model_copy(update={"draft": draft}))
    assert any(failure.startswith(expected) for failure in failures), failures


def test_null_mapping_is_not_reported_as_proof_of_missing_taxonomy(taxonomy):
    case = CASES["context-programming-project"]
    result = interpret(case, taxonomy)
    result = result.model_copy(
        update={
            "draft": result.draft.model_copy(
                update={
                    "competencies": [
                        result.draft.competencies[0].model_copy(
                            update={"competency_id": None}
                        )
                    ]
                }
            )
        }
    )
    assert coverage_gaps(result, taxonomy)[0]["reason"] == "unmapped_skill_needs_review"
    assert "claim[1]:false_negative_competency:programming" in compare(case, result)


def test_invalid_source_anchor_cannot_be_used_as_reference(taxonomy):
    case = CASES["context-tool-only"]
    case = case.model_copy(
        update={
            "claim_expectations": [
                case.claim_expectations[0].model_copy(
                    update={"source_quote": "Invented passage"}
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="source quotes"):
        validate_case(case, taxonomy)
