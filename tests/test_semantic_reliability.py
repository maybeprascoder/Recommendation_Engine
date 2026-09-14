"""Provisional semantic boundaries; recorded paths do not prove model accuracy."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from qa.cross_domain_evidence import (
    classify_outcomes,
    compare,
    interpret,
    load_suite,
    project,
    training_records,
    validate_case,
)
from unihive.competency import resolve_competencies
from unihive.models import EvidenceState
from unihive.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[1]
SUITE = load_suite(ROOT / "tests/fixtures/understanding/semantic_reliability.json")
CASES = {case.id: case for case in SUITE.cases}
TOOLS = {
    "etabs",
    "autocad",
    "ansys",
    "solidworks",
    "matlab",
    "arduino",
    "verilog",
    "wireshark",
    "nessus",
    "kali",
    "tensorflow",
    "pytorch",
    "react",
    "sql",
    "aws",
    "python",
}


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def supported_label(result, dimension):
    return {
        item.label
        for item in result.draft.judgments
        if item.dimension == dimension and item.id in result.supported_judgment_ids
    } or {"unknown"}


def test_suite_is_provisional_balanced_and_has_exact_live_set():
    assert SUITE.provisional and SUITE.validated_by is None and SUITE.source is None
    assert len(SUITE.cases) == 77
    assert sum(case.live_focus for case in SUITE.cases) == 14
    assert {case.id for case in SUITE.cases if case.live_focus} == {
        "tool-etabs-bare",
        "evaluation-civil",
        "impact-civil-measured",
        "tool-nessus-bare",
        "mixed-cyber-python",
        "tool-pytorch-bare",
        "mixed-ml-strong",
        "mixed-civil-python",
        "ownership-team-ambiguous",
        "ownership-led-team",
        "publication-unspecified-review",
        "publication-explicit-peer-review",
        "absence-python",
        "absence-publication",
    }
    assert all(case.validated_by is None for case in SUITE.cases)
    assert all("human_authored" in case.annotation_status for case in SUITE.cases)


@pytest.mark.parametrize("case", SUITE.cases, ids=CASES)
def test_all_references_pass_existing_pipeline(case, taxonomy):
    validate_case(case, taxonomy)
    result = interpret(case, taxonomy)
    assert not compare(case, result)
    assert result.audit.prompt_version == "understanding-v9+support-review-v9"


@pytest.mark.parametrize("case", SUITE.cases, ids=CASES)
def test_all_adversarial_proposals_are_rejected(case, taxonomy):
    result = interpret(case, taxonomy, challenge=True)
    supported = {
        *result.supported_claim_ids,
        *result.supported_judgment_ids,
        *result.supported_competency_ids,
        *result.supported_context_ids,
    }
    assert not supported.intersection(case.review_challenge.rejected_ids)


@pytest.mark.parametrize(
    "case_id",
    [
        "evaluation-civil",
        "evaluation-cybersecurity",
        "evaluation-machine_learning",
        "evaluation-mechanical",
        "evaluation-electrical",
        "impact-evaluation-only",
    ],
)
def test_comparison_is_evaluation_without_impact(case_id, taxonomy):
    result = interpret(CASES[case_id], taxonomy)
    assert supported_label(result, "evaluation") == {"compared"}
    assert supported_label(result, "impact") == {"unknown"}
    profile = project(result, taxonomy)
    assert not any(
        item.qualitative_mapping
        and any(
            judgment.dimension == "impact"
            and judgment.id in item.qualitative_mapping.judgment_ids
            for judgment in result.draft.judgments
        )
        for item in profile.evidence
    )


@pytest.mark.parametrize(
    "case_id,expected",
    [
        ("impact-evaluation-only", "unknown"),
        ("impact-reported-outcome", "reported"),
        ("impact-measured-outcome", "measured"),
        ("impact-adopted", "adopted"),
    ],
)
def test_impact_boundaries_are_distinct(case_id, expected, taxonomy):
    result = interpret(CASES[case_id], taxonomy)
    assert supported_label(result, "impact") == {expected}


@pytest.mark.parametrize(
    "verb", ["designed", "implemented", "developed", "built", "created"]
)
def test_personal_execution_does_not_become_leadership(verb, taxonomy):
    result = interpret(CASES[f"ownership-execution-{verb}"], taxonomy)
    assert supported_label(result, "ownership") == {"unknown"}
    assert result.supported_competency_ids


@pytest.mark.parametrize(
    "case_id",
    [
        "ownership-led-team",
        "ownership-owned-delivery",
        "ownership-sole-delivery",
        "ownership-project-lead",
    ],
)
def test_explicit_leadership_is_preserved_without_numeric_reward(case_id, taxonomy):
    result = interpret(CASES[case_id], taxonomy)
    assert supported_label(result, "ownership") == {"led"}
    for item in project(result, taxonomy).evidence:
        if item.qualitative_mapping:
            assert all(
                judgment.dimension != "ownership"
                for judgment in result.draft.judgments
                if judgment.id in item.qualitative_mapping.judgment_ids
            )


def test_ambiguous_team_outcome_has_no_student_credit(taxonomy):
    result = interpret(CASES["ownership-team-ambiguous"], taxonomy)
    assert result.draft.claims[0].attribution.value == "team"
    assert supported_label(result, "ownership") == {"unknown"}
    assert not result.supported_competency_ids
    assert result.questions


def test_oracle_catches_team_outcome_promoted_to_student(taxonomy):
    case = CASES["ownership-team-ambiguous"]
    result = interpret(case, taxonomy)
    claim = result.draft.claims[0].model_copy(update={"attribution": "student"})
    failures = compare(
        case,
        result.model_copy(
            update={"draft": result.draft.model_copy(update={"claims": [claim]})}
        ),
    )
    assert "claim[1]:attribution:expected team, got student" in failures
    assert "semantic_false_positive" in classify_outcomes(failures)


def test_publication_does_not_imply_review_or_impact(taxonomy):
    unspecified = interpret(CASES["publication-unspecified-review"], taxonomy)
    assert supported_label(unspecified, "evaluation") == {"unknown"}
    assert supported_label(unspecified, "impact") == {"unknown"}
    assert not unspecified.supported_competency_ids
    explicit = interpret(CASES["publication-explicit-peer-review"], taxonomy)
    assert supported_label(explicit, "evaluation") == {"externally_reviewed"}
    assert supported_label(explicit, "impact") == {"unknown"}
    assert all("Journal XYZ" in item.label for item in explicit.draft.contexts)
    assert any("quality" in value.lower() for value in explicit.draft.unassessed)
    assert not compare(CASES["publication-unspecified-review"], unspecified)
    missing = unspecified.model_copy(
        update={"draft": unspecified.draft.model_copy(update={"unassessed": []})}
    )
    assert {
        "claim[1]:missing_uncertainty:venue",
        "claim[1]:missing_uncertainty:acceptance",
        "claim[1]:missing_uncertainty:citation",
    }.issubset(compare(CASES["publication-unspecified-review"], missing))


@pytest.mark.parametrize(
    "case_id", ["absence-python", "absence-publication", "absence-internship"]
)
def test_absence_remains_exact_and_never_becomes_competency_absence(case_id, taxonomy):
    result = interpret(CASES[case_id], taxonomy)
    assert result.draft.claims[0].presence.value == "reported_absent"
    assert not result.supported_judgment_ids and not result.supported_competency_ids
    profile = project(result, taxonomy)
    imported = [item for item in profile.evidence if item.source_claim_id == "c1"]
    assert len(imported) == 1
    assert imported[0].state == EvidenceState.CONFIRMED_ABSENT
    assert imported[0].raw_text == CASES[case_id].source_text
    assert imported[0].scoring_exclusion == "awaiting_approved_mapping"
    assert all(
        item.state == EvidenceState.UNKNOWN
        for item in resolve_competencies(profile, taxonomy, as_of=date(2026, 9, 13))
    )


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_bare_tool_is_context_only(tool, taxonomy):
    result = interpret(CASES[f"tool-{tool}-bare"], taxonomy)
    assert result.supported_context_ids
    assert not result.supported_competency_ids
    assert supported_label(result, "depth") == {"unknown"}
    assert result.questions
    assert not any(
        item.qualitative_mapping for item in project(result, taxonomy).evidence
    )


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_explicit_tool_method_survives_as_skill_or_unmapped_skill(tool, taxonomy):
    result = interpret(CASES[f"tool-{tool}-activity"], taxonomy)
    assert result.supported_context_ids and result.supported_competency_ids
    assert supported_label(result, "depth") == {"applied"}
    assert supported_label(result, "ownership") == {"unknown"}


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_explicit_independent_tool_work_is_distinct_from_bare_context(tool, taxonomy):
    result = interpret(CASES[f"tool-{tool}-independent"], taxonomy)
    assert result.supported_context_ids and result.supported_competency_ids
    assert supported_label(result, "ownership") == {"led"}
    assert supported_label(result, "depth") == {"applied"}


@pytest.mark.parametrize(
    "case_id,expected_nodes",
    [
        ("mixed-civil-python", {"programming", "structural_analysis"}),
        ("mixed-cyber-python", {"programming", "security"}),
        (
            "mixed-mechanical-matlab",
            {"programming", "engineering_simulation"},
        ),
        ("mixed-ml-strong", {"machine_learning"}),
    ],
)
def test_mixed_domain_programming_and_methods_are_both_retained(
    case_id, expected_nodes, taxonomy
):
    result = interpret(CASES[case_id], taxonomy)
    nodes = {
        item.competency_id
        for item in result.draft.competencies
        if item.id in result.supported_competency_ids and item.competency_id
    }
    assert nodes == expected_nodes
    assert all(
        item.competency_id is not None
        for item in result.draft.competencies
        if item.id in result.supported_competency_ids
    )
    assert result.supported_context_ids


def test_cyber_method_oracle_accepts_security_or_networking_but_requires_one(
    taxonomy,
):
    case = CASES["mixed-cyber-python"]
    result = interpret(case, taxonomy)
    security = next(
        item for item in result.draft.competencies if item.competency_id == "security"
    )
    networking = security.model_copy(update={"competency_id": "networking"})
    swapped = result.model_copy(
        update={
            "draft": result.draft.model_copy(
                update={
                    "competencies": [
                        networking if item.id == security.id else item
                        for item in result.draft.competencies
                    ]
                }
            )
        }
    )
    assert not compare(case, swapped)
    missing = result.model_copy(
        update={
            "supported_competency_ids": [
                item
                for item in result.supported_competency_ids
                if item != security.id
            ]
        }
    )
    failures = compare(case, missing)
    assert any(
        "missing_competency_group:networking,security" in item for item in failures
    )
    assert "semantic_false_negative" in classify_outcomes(failures)


def test_oracle_and_outcome_classifier_separate_failure_types(taxonomy):
    case = CASES["evaluation-civil"]
    result = interpret(case, taxonomy)
    draft = result.draft.model_copy(
        update={
            "judgments": [
                item.model_copy(update={"label": "reported"})
                if item.dimension == "impact"
                else item
                for item in result.draft.judgments
            ]
        }
    )
    impact_id = next(j.id for j in draft.judgments if j.dimension == "impact")
    changed = result.model_copy(
        update={
            "draft": draft,
            "supported_judgment_ids": [*result.supported_judgment_ids, impact_id],
        }
    )
    failures = compare(case, changed)
    assert any("impact:expected unknown, got reported" in item for item in failures)
    assert classify_outcomes(failures) == [
        "structurally_valid",
        "semantic_false_positive",
    ]
    assert classify_outcomes([]) == ["structurally_valid", "clean_pass"]


def test_training_export_is_qualitative_and_never_uses_model_predictions_as_gold():
    forbidden = {
        "competency_contributions",
        "contribution",
        "student_score",
        "admission_probability",
        "fit_score",
        "target_relevance",
    }

    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    for case in SUITE.cases:
        records = training_records(case)
        assert not keys(records).intersection(forbidden)
        assert all(
            item["annotation_status"]
            == "provisional_human_authored_synthetic_reference"
            for item in records
        )
        assert all(
            item["annotation_schema_version"] == "understanding-v3" for item in records
        )
        assert all("model_output" not in item for item in records)


def test_runtime_instrumentation_records_calls_without_source_text():
    from pydantic import JsonValue

    from qa.cross_domain_evidence import InstrumentedClient
    from unihive.llm.provider import Completion, ProviderError

    class Client:
        provider = "test"
        model = "test"

        def complete(
            self,
            *,
            instructions: str,
            payload: str,
            schema: dict[str, JsonValue],
            name: str,
        ) -> Completion:
            if name == "fail":
                raise ProviderError("Model endpoint unavailable or timed out")
            return Completion(text="{}", response_id="id", model="test")

    client = InstrumentedClient(Client())
    client.complete(
        instructions="private instructions",
        payload="private source",
        schema={"type": "object"},
        name="ok",
    )
    with pytest.raises(ProviderError):
        client.complete(
            instructions="private instructions",
            payload="private source",
            schema={"type": "object"},
            name="fail",
        )
    assert [item["status"] for item in client.calls] == [
        "completed",
        "provider_error",
    ]
    assert [item["name"] for item in client.calls] == ["ok", "fail"]
    assert "private" not in str(client.calls)


def test_live_focus_selector_runs_exactly_the_declared_cases_offline(tmp_path):
    output = tmp_path / "focused"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "qa.cross_domain_evidence",
            "--suite",
            str(ROOT / "tests/fixtures/understanding/semantic_reliability.json"),
            "--live-focus",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    rows = json.loads((output / "results.json").read_text("utf-8"))
    assert len(rows) == 14
    assert all(row["outcomes"] == ["structurally_valid", "clean_pass"] for row in rows)
