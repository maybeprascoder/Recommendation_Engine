"""Stage 3 provisional taxonomy expansion and false-positive boundaries."""

from datetime import date
from pathlib import Path

import pytest

from qa.cross_domain_evidence import (
    compare,
    coverage_gaps,
    interpret,
    load_suite,
    project,
)
from unihive.competency import resolve_competencies
from unihive.models import EvidenceState
from unihive.taxonomy import load_taxonomy
from unihive.understanding import CompetencySuggestion

NEW_NODE_IDS = {
    "structural_analysis",
    "structural_design",
    "mechanical_design",
    "engineering_simulation",
    "embedded_digital_systems",
    "qualitative_research",
    "teaching_instruction",
}
SEMANTIC_FIXTURE = (
    Path(__file__).parent / "fixtures/understanding/semantic_reliability.json"
)
TOOL_NAMES = {
    "ansys",
    "arduino",
    "autocad",
    "etabs",
    "matlab",
    "nessus",
    "pytorch",
    "solidworks",
    "wireshark",
}


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


@pytest.fixture(scope="module")
def semantic_cases():
    suite = load_suite(SEMANTIC_FIXTURE)
    return {case.id: case for case in suite.cases}


@pytest.fixture(scope="module")
def cross_domain_cases():
    suite = load_suite()
    return {case.id: case for case in [*suite.cases, *suite.probes]}


def supported_nodes(case) -> set[str]:
    supported = set(case.expected_supported_ids.competencies)
    return {
        item.competency_id
        for item in case.expected_understanding.competencies
        if item.id in supported and item.competency_id is not None
    }


def test_new_nodes_are_provisional_and_have_explicit_boundaries(taxonomy):
    nodes = {node.id: node for node in taxonomy.competencies}
    assert NEW_NODE_IDS <= nodes.keys()
    for node_id in NEW_NODE_IDS:
        node = nodes[node_id]
        assert node.provisional and node.validated_by is None and node.source is None
        assert node.description
        assert len(node.supporting_evidence) >= 2
        assert len(node.insufficient_evidence) >= 2
        assert len(node.common_false_positive_traps) >= 2


def test_aliases_preserve_structural_and_cross_domain_distinctions(taxonomy):
    assert taxonomy.lookup_by_alias("structural analysis").id == "structural_analysis"
    assert taxonomy.lookup_by_alias("load analysis").id == "structural_analysis"
    assert taxonomy.lookup_by_alias("structural design").id == "structural_design"
    assert taxonomy.lookup_by_alias("thematic coding").id == "qualitative_research"
    assert taxonomy.lookup_by_alias("tutoring").id == "teaching_instruction"
    assert taxonomy.lookup_by_id("structural_analysis") != taxonomy.lookup_by_id(
        "structural_design"
    )


def test_tools_are_not_competency_nodes_or_aliases(taxonomy):
    node_ids = {node.id for node in taxonomy.competencies}
    node_names = {node.name.casefold() for node in taxonomy.competencies}
    assert not TOOL_NAMES.intersection(node_ids)
    assert not TOOL_NAMES.intersection(node_names)
    assert not TOOL_NAMES.intersection(taxonomy.aliases)


def test_new_nodes_have_no_deterministic_scoring_routes(taxonomy):
    routed = {rule.competency_id for rule in taxonomy.evidence_rules}
    assert not NEW_NODE_IDS.intersection(routed)


def test_existing_nodes_are_reused_before_new_nodes(
    semantic_cases, cross_domain_cases
):
    assert supported_nodes(cross_domain_cases["ml-deep"]) >= {"machine_learning"}
    assert supported_nodes(cross_domain_cases["sql-analysis"]) == {"programming"}
    assert supported_nodes(cross_domain_cases["cyber-investigation"]) == {
        "networking",
        "security",
    }
    assert supported_nodes(semantic_cases["mixed-cyber-python"]) == {
        "programming",
        "security",
    }


def test_only_deliberately_deferred_methods_remain_uncatalogued(
    semantic_cases, cross_domain_cases
):
    remaining = {
        item.observed_skill
        for case in [*semantic_cases.values(), *cross_domain_cases.values()]
        for item in case.expected_understanding.competencies
        if item.id in case.expected_supported_ids.competencies
        and item.competency_id is None
    }
    assert remaining == {"Technical drafting", "Cloud deployment", "workflow design"}


def test_bare_tools_remain_context_only(semantic_cases, taxonomy):
    bare_cases = [
        case for case in semantic_cases.values() if case.id.endswith("-bare")
    ]
    assert len(bare_cases) == 16
    for case in bare_cases:
        result = interpret(case, taxonomy)
        assert result.supported_context_ids
        assert not result.supported_competency_ids


def test_structural_method_resolves_without_activating_scoring(
    semantic_cases, taxonomy
):
    case = semantic_cases["tool-etabs-activity"]
    result = interpret(case, taxonomy)
    assert supported_nodes(case) == {"structural_analysis"}
    assert {item["reason"] for item in coverage_gaps(result, taxonomy)} == {
        "qualitative_route_missing"
    }
    resolved = next(
        item
        for item in resolve_competencies(
            project(result, taxonomy), taxonomy, as_of=date(2026, 9, 14)
        )
        if item.competency_id == "structural_analysis"
    )
    assert resolved.state == EvidenceState.UNKNOWN
    assert not resolved.explanation_trace


def test_quantitative_analysis_is_not_inferred_from_domain_calculation(
    semantic_cases, taxonomy
):
    case = semantic_cases["mixed-civil-python"]
    result = interpret(case, taxonomy)
    assert "quantitative_analysis" not in supported_nodes(case)
    citation = result.draft.claims[0].citations
    suggestion = CompetencySuggestion(
        id="false-quantitative-analysis",
        claim_id=result.draft.claims[0].id,
        competency_id="quantitative_analysis",
        observed_skill="structural loads are numeric",
        rationale="The source contains a calculation.",
        citations=citation,
    )
    changed = result.model_copy(
        update={
            "draft": result.draft.model_copy(
                update={
                    "competencies": [*result.draft.competencies, suggestion]
                }
            ),
            "supported_competency_ids": [
                *result.supported_competency_ids,
                suggestion.id,
            ],
        }
    )
    assert (
        "claim[1]:false_positive_competency:quantitative_analysis"
        in compare(case, changed)
    )
