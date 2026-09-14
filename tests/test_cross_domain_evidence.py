"""Cross-domain calibration separates semantic references from numeric probes."""

import json
from collections import Counter
from decimal import Decimal

import pytest

from qa.cross_domain_evidence import (
    AS_OF,
    compare,
    coverage_gaps,
    empty_profile,
    interpret,
    load_suite,
    project,
    training_records,
    validate_case,
)
from unihive.competency import resolve_competencies
from unihive.evidence import (
    EvidenceConfigurationError,
    load_evidence_configuration,
)
from unihive.models import Confidence, Evidence, EvidenceState
from unihive.taxonomy import load_taxonomy
from unihive.understanding import CompetencySuggestion, EvidenceCategory

SUITE = load_suite()
CASES = {case.id: case for case in [*SUITE.cases, *SUITE.probes]}


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def test_balanced_domains_and_explicit_tool_method_separation():
    assert Counter(c.domain for c in SUITE.cases) == {
        "software": 4,
        "machine_learning": 4,
        "cybersecurity": 4,
        "civil": 4,
        "electrical": 3,
        "mechanical": 3,
        "interdisciplinary": 3,
    }
    assert {
        tool for c in CASES.values() for tool in c.semantic_context.recognized_tools
    } >= {
        "AutoCAD",
        "ETABS",
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
    }
    assert SUITE.provisional and SUITE.validated_by is None


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_golden_reference_through_existing_pipeline(case, taxonomy):
    validate_case(case, taxonomy)
    result = interpret(case, taxonomy)
    assert not compare(case, result)
    profile = project(result, taxonomy)
    assert all(e.state == EvidenceState.SELF_REPORTED_PRESENT for e in profile.evidence)
    assert all(e.state != EvidenceState.CONFIRMED_ABSENT for e in profile.evidence)
    assert len(result.audit.response_ids) == 2
    supported = set(result.supported_judgment_ids)
    for item in profile.evidence:
        if item.qualitative_mapping:
            assert set(item.qualitative_mapping.judgment_ids) <= supported
    competencies = resolve_competencies(profile, taxonomy, as_of=AS_OF)
    for node in case.forbidden_competency_ids:
        assert (
            next(c for c in competencies if c.competency_id == node).state
            == EvidenceState.UNKNOWN
        )


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_injected_hallucinations_are_removed_by_mocked_support_review(case, taxonomy):
    result = interpret(case, taxonomy, challenge=True)
    accepted = {
        *result.supported_claim_ids,
        *result.supported_judgment_ids,
        *result.supported_competency_ids,
    }
    assert not accepted.intersection(case.review_challenge.rejected_ids)
    mapped = [e for e in project(result, taxonomy).evidence if e.qualitative_mapping]
    assert all(
        not set(e.qualitative_mapping.judgment_ids).intersection(
            case.review_challenge.rejected_ids
        )
        for e in mapped
    )
    assert all(
        not set(e.qualitative_mapping.competency_suggestion_ids).intersection(
            case.review_challenge.rejected_ids
        )
        for e in mapped
    )
    if case.review_challenge.rejected_ids:
        assert result.questions


@pytest.mark.parametrize("case_id", [key for key in CASES if key.startswith("tool-")])
def test_tool_names_create_neither_methods_nor_scored_competencies(case_id, taxonomy):
    case = CASES[case_id]
    assert not case.semantic_context.methods_performed
    result = interpret(case, taxonomy)
    assert not result.supported_judgment_ids and not result.supported_competency_ids
    assert result.questions
    assert all(
        c.state == EvidenceState.UNKNOWN
        for c in resolve_competencies(project(result, taxonomy), taxonomy, as_of=AS_OF)
    )


@pytest.mark.parametrize(
    "case_id,reason",
    [
        ("civil-deep", "unmapped_skill_needs_review"),
        ("electrical-deep", "unmapped_skill_needs_review"),
        ("mechanical-deep", "unmapped_skill_needs_review"),
        ("cyber-basic", "qualitative_route_missing"),
        ("neutral-teaching", "unmapped_skill_needs_review"),
    ],
)
def test_coverage_failure_is_not_failed_student_evidence(case_id, reason, taxonomy):
    result = interpret(CASES[case_id], taxonomy)
    assert result.supported_judgment_ids and result.supported_competency_ids
    assert reason in {item["reason"] for item in coverage_gaps(result, taxonomy)}
    profile = project(result, taxonomy)
    assert profile.evidence
    assert not any(e.qualitative_mapping for e in profile.evidence)
    assert all(
        c.state == EvidenceState.UNKNOWN
        for c in resolve_competencies(profile, taxonomy, as_of=AS_OF)
    )


@pytest.mark.parametrize(
    "case_id,expected_present",
    [
        ("neutral-civil-python", {"programming"}),
        ("cyber-deep", {"programming"}),
        ("software-api-design", {"programming"}),
        ("civil-designed", set()),
        ("mechanical-deep", set()),
        ("sql-analysis", set()),
    ],
)
def test_general_purpose_tools_do_not_force_unrelated_competencies(
    case_id, expected_present, taxonomy
):
    result = interpret(CASES[case_id], taxonomy)
    competencies = resolve_competencies(
        project(result, taxonomy), taxonomy, as_of=AS_OF
    )
    assert {
        c.competency_id
        for c in competencies
        if c.state == EvidenceState.SELF_REPORTED_PRESENT
    } == expected_present


def intrinsic_probe(case, taxonomy):
    """Test-only missing-node scenario; never modify production fixtures/catalog.

    Reuse exact shipped label requirements, priority and numeric configuration.
    This proves machinery monotonicity if a domain route is configured, not current
    domain coverage. The synthetic node has no asserted academic definition.
    """
    target = "synthetic_calibration_only"
    node = taxonomy.lookup_by_id("programming").model_copy(
        update={
            "id": target,
            "name": "Test-only calibration target",
            "source": None,
            "description": "Synthetic arithmetic probe, not a production competency.",
        }
    )
    rule = next(
        r for r in taxonomy.evidence_rules if r.competency_id == "programming"
    ).model_copy(
        update={
            "id": "synthetic-calibration-route",
            "evidence_kind": "synthetic-calibration",
            "competency_id": target,
            "source": None,
        }
    )
    mappings = tuple(
        m.model_copy(
            update={
                "id": "synthetic-" + m.id,
                "evidence_rule_id": rule.id,
                "claim_category": case.expected_understanding.claims[0].category.value,
            }
        )
        for m in taxonomy.qualitative_mappings
        if m.claim_category == "project"
        and m.evidence_rule_id == "qualitative_activity_to_programming"
    )
    sandbox = taxonomy.model_copy(
        update={
            "competencies": (*taxonomy.competencies, node),
            "evidence_rules": (rule,),
            "qualitative_mappings": mappings,
        }
    )
    draft = case.expected_understanding.model_copy(
        update={
            "competencies": [
                s.model_copy(update={"competency_id": target})
                for s in case.expected_understanding.competencies
            ],
        }
    )
    modified = case.model_copy(update={"expected_understanding": draft})
    profile = project(interpret(modified, sandbox), sandbox)
    result = next(
        c
        for c in resolve_competencies(profile, sandbox, as_of=AS_OF)
        if c.competency_id == target
    )
    if not result.explanation_trace:
        assert result.state == EvidenceState.UNKNOWN
        return None
    return sum((t.contribution for t in result.explanation_trace), Decimal(0))


PROGRESSIONS = [
    [
        "software-tool",
        "software-basic",
        "software-api-design",
        "software-deep-duplicate",
    ],
    ["ml-tool", "ml-basic", "ml-compared", "ml-deep"],
    ["cyber-tool", "cyber-basic", "cyber-investigation", "cyber-deep"],
    ["civil-tool", "civil-basic", "civil-designed", "civil-deep"],
    ["mechanical-tool", "mechanical-model", "mechanical-deep"],
    ["electrical-tool", "electrical-basic", "electrical-deep"],
]


@pytest.mark.parametrize(
    "progression", PROGRESSIONS, ids=[p[0].split("-")[0] for p in PROGRESSIONS]
)
def test_qualitative_mapping_monotonicity_with_explicit_coverage_probe(
    progression, taxonomy
):
    values = [intrinsic_probe(CASES[key], taxonomy) for key in progression]
    assert values[0] is None  # unassessed is never numerical zero
    scored = values[1:]
    assert all(value is not None for value in scored)
    assert scored == sorted(scored)
    assert scored[-1] > scored[0]


@pytest.mark.parametrize(
    "progression,node",
    [
        (PROGRESSIONS[0], "programming"),
        (PROGRESSIONS[1], "machine_learning"),
    ],
)
def test_production_progression_where_routes_exist(progression, node, taxonomy):
    values = []
    for case_id in progression:
        profile = project(interpret(CASES[case_id], taxonomy), taxonomy)
        result = next(
            c
            for c in resolve_competencies(profile, taxonomy, as_of=AS_OF)
            if c.competency_id == node
        )
        if result.state == EvidenceState.UNKNOWN:
            assert not result.explanation_trace
            continue
        values.append(
            sum((t.contribution for t in result.explanation_trace), Decimal(0))
        )
    assert values == sorted(values)
    assert values[-1] > values[0]


def test_mapping_plateaus_are_documented_without_inventing_extra_weights(taxonomy):
    # These distinguishable qualitative patterns share the current middle tier.
    ids = [
        "civil-designed",
        "ml-compared",
        "cyber-investigation",
        "nessus-design",
        "measured-no-comparison",
        "neutral-research-absence",
    ]
    values = [intrinsic_probe(CASES[key], taxonomy) for key in ids]
    assert values[0] is not None
    assert len(set(values)) == 1


def contribution(profile, taxonomy, node="programming"):
    result = next(
        c
        for c in resolve_competencies(profile, taxonomy, as_of=AS_OF)
        if c.competency_id == node
    )
    return sum((t.contribution for t in result.explanation_trace), Decimal(0))


def repeated_independent_evidence(profile, count):
    evidence = next(e for e in profile.evidence if e.qualitative_mapping)
    return profile.model_copy(
        update={
            "evidence": [
                evidence.model_copy(
                    update={
                        "id": f"independent-{index}",
                        "source_claim_id": f"independent-claim-{index}",
                    }
                )
                for index in range(count)
            ]
        }
    )


def test_duplicates_do_not_double_score_and_independent_evidence_accumulates(taxonomy):
    case = CASES["software-deep-duplicate"]
    result = interpret(case, taxonomy)
    profile = project(result, taxonomy)
    assert result.supported_claim_ids == ["c1"]
    assert len([e for e in profile.evidence if e.qualitative_mapping]) == 1
    totals = [
        contribution(repeated_independent_evidence(profile, n), taxonomy)
        for n in [1, 2, 3, 4]
    ]
    assert totals == sorted(set(totals))
    assert totals[-1] < totals[0] * 4
    # Student confirmation edits cannot turn the duplicate into independent work.
    assert contribution(project(result, taxonomy), taxonomy) == totals[0]


def test_many_shallow_activities_cannot_linearly_overpower_one_deep_activity(taxonomy):
    shallow = project(interpret(CASES["software-basic"], taxonomy), taxonomy)
    deep = project(interpret(CASES["software-deep-duplicate"], taxonomy), taxonomy)
    assert contribution(
        repeated_independent_evidence(shallow, 60), taxonomy
    ) < contribution(deep, taxonomy)
    assert contribution(
        repeated_independent_evidence(shallow, 1000), taxonomy
    ) < contribution(deep, taxonomy)
    configuration = load_evidence_configuration(taxonomy.evidence_configuration)
    curve = configuration.combination_curve
    assert curve.multiplier_at(4) < curve.multiplier_at(3)
    legacy = curve.model_copy(update={"tail_mode": "constant"})
    assert legacy.multiplier_at(4) == legacy.multiplier_at(3)


def test_geometric_tail_requires_a_strictly_decreasing_ratio(taxonomy):
    config = dict(taxonomy.evidence_configuration)
    config["combination_curve"] = {
        "multipliers": [1],
        "tail_multiplier": 1,
        "tail_mode": "geometric",
    }
    with pytest.raises(EvidenceConfigurationError, match="geometric tail"):
        load_evidence_configuration(config)


def test_confirmed_absence_is_distinct_from_unassessed_without_positive_credit(
    taxonomy,
):
    case = CASES["neutral-research-absence"]
    result = interpret(case, taxonomy)
    assert case.confirmed_absence
    assert "not written programming code" in result.draft.claims[0].statement
    assert not any(e.qualitative_mapping for e in project(result, taxonomy).evidence)
    # The current draft has no typed absence field. Test existing explicit state
    # handling separately; do not pretend interpretation already projects absence.
    for state in [EvidenceState.UNKNOWN, EvidenceState.CONFIRMED_ABSENT]:
        evidence = Evidence(
            id="absence",
            kind="qualitative_programming_activity",
            raw_text=case.source_text,
            state=state,
            quality=None,
            depth=None,
            recency=None,
            source=case.source_text,
            extraction_confidence=Confidence.LOW,
        )
        profile = empty_profile().model_copy(update={"evidence": [evidence]})
        competency = next(
            c
            for c in resolve_competencies(profile, taxonomy, as_of=AS_OF)
            if c.competency_id == "programming"
        )
        assert competency.state == state and competency.level is None
        assert competency.explanation_trace[0].contribution is None


def test_training_export_excludes_all_scoring_targets_and_keeps_grounded_schema():
    forbidden = {
        "score",
        "quality",
        "depth_factor",
        "verification_factor",
        "priority",
        "contribution",
        "student_score",
        "admission_probability",
        "fit_score",
    }

    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    for case in CASES.values():
        records = training_records(case)
        assert not keys(records).intersection(forbidden)
        assert records[0]["input"] == case.source_text
        assert records[0]["expected_output"] == case.expected_understanding.model_dump(
            mode="json", exclude_unset=True
        )
        assert records[0]["annotation_schema_version"] == "understanding-v2"
        assert "contexts" not in records[0]["expected_output"]
        assert all("presence" not in c for c in records[0]["expected_output"]["claims"])
        assert records[1][
            "expected_output"
        ] == case.review_challenge.expected_review.model_dump(mode="json")
        assert json.loads(json.dumps(records)) == records


def test_oracle_detects_false_positive_and_false_negative_competency_outputs(taxonomy):
    result = interpret(CASES["software-api-design"], taxonomy)
    wrong = result.draft.competencies[0].model_copy(
        update={"competency_id": "machine_learning"}
    )
    altered = result.model_copy(
        update={"draft": result.draft.model_copy(update={"competencies": [wrong]})}
    )
    failures = compare(CASES["software-api-design"], altered)
    assert "false_positive_competency:machine_learning" in failures
    assert "false_negative_competency:programming" in failures


def test_oracle_does_not_hide_unsupported_labels_on_another_claim(taxonomy):
    case = CASES["neutral-research-absence"]
    result = interpret(case, taxonomy)
    comparison = next(j for j in result.draft.judgments if j.dimension == "evaluation")
    invented = comparison.model_copy(
        update={
            "id": "invented-review",
            "claim_id": "other-claim",
            "label": "externally_reviewed",
        }
    )
    changed = result.model_copy(
        update={
            "draft": result.draft.model_copy(
                update={"judgments": [invented, *result.draft.judgments]}
            ),
            "supported_judgment_ids": [*result.supported_judgment_ids, invented.id],
        }
    )
    assert any("externally_reviewed" in error for error in compare(case, changed))


def test_oracle_catches_tool_only_null_skill_and_activity_asks_for_method(taxonomy):
    case = CASES["tool-nessus"]
    draft = case.expected_understanding.model_copy(
        update={
            "claims": [
                case.expected_understanding.claims[0].model_copy(
                    update={"category": EvidenceCategory.ACTIVITY}
                )
            ],
            "questions": [],
        }
    )
    result = interpret(
        case.model_copy(update={"expected_understanding": draft}), taxonomy
    )
    assert result.questions and "personally do" in result.questions[0].question
    skill = CompetencySuggestion(
        id="tool-skill",
        claim_id="c1",
        competency_id=None,
        observed_skill="Nessus usage",
        rationale="Tool recognition only.",
        citations=draft.claims[0].citations,
    )
    changed = result.model_copy(
        update={
            "draft": result.draft.model_copy(update={"competencies": [skill]}),
            "supported_competency_ids": [skill.id],
        }
    )
    assert "tool_recognition_promoted_to_demonstrated_skill" in compare(case, changed)
