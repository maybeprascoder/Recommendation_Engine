"""Mocked two-pass interpretation through confirmation, scoring and replay."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from test_competency import profile_with
from understanding_samples import qualitative_result

from unihive.audit import create_audited_assessment, replay_assessment
from unihive.competency import resolve_competencies
from unihive.eligibility import load_program_config
from unihive.evidence import evaluate_evidence, load_evidence_configuration
from unihive.models import Evidence, EvidenceState, StudentProfile
from unihive.scoring import load_scoring_configuration
from unihive.taxonomy import Taxonomy, load_taxonomy
from unihive.understanding import UnderstandingResult
from unihive.understanding_review import (
    ClaimDecision,
    confirm_understanding,
    initial_academic_corrections,
    initial_claim_corrections,
    initial_judgment_corrections,
)

AS_OF = date(2026, 9, 11)
BERT = (
    "Designed a multilingual BERT classifier, compared four baselines, "
    "improved F1 by 12%, and deployed it to production."
)
PUBLICATION = (
    "First author of a transformer image-segmentation paper published in Journal XYZ."
)


def confirm(
    result: UnderstandingResult,
    taxonomy: Taxonomy | None = None,
    profile: StudentProfile | None = None,
) -> StudentProfile:
    return confirm_understanding(
        profile or profile_with([]),
        result,
        initial_claim_corrections(result),
        initial_academic_corrections(result),
        initial_judgment_corrections(result),
        taxonomy or load_taxonomy(),
    )


def mapped(profile: StudentProfile) -> list[Evidence]:
    return [item for item in profile.evidence if item.qualitative_mapping is not None]


def bert_result(**kwargs) -> UnderstandingResult:
    return qualitative_result(
        BERT,
        labels={"depth": "designed", "evaluation": "compared", "impact": "measured"},
        skills={"ML": "machine_learning", "NLP": None},
        **kwargs,
    )


def test_todo_is_basic_self_reported_without_invented_ownership_or_impact() -> None:
    result = qualitative_result(
        "Built a TODO app using React.",
        labels={"depth": "applied"},
        skills={"React implementation": "programming"},
    )
    labels = {j.dimension: j.label for j in result.draft.judgments}
    assert labels == {
        "depth": "applied",
        "ownership": "unknown",
        "evaluation": "unknown",
        "impact": "unknown",
    }
    profile = confirm(result)
    (evidence,) = mapped(profile)
    assert evidence.quality == "basic" and evidence.depth == "applied"
    assert evidence.scoring_exclusion is None
    assert evidence.state == EvidenceState.SELF_REPORTED_PRESENT
    assert evidence.qualitative_mapping.judgment_ids == ["depth"]
    competencies = resolve_competencies(profile, load_taxonomy(), as_of=AS_OF)
    programming = next(c for c in competencies if c.competency_id == "programming")
    assert programming.level.name == "INTRODUCTORY"
    assert programming.explanation_trace[0].verification == Decimal("0.8")
    assert (
        next(c for c in competencies if c.competency_id == "machine_learning").state
        == EvidenceState.UNKNOWN
    )


@pytest.mark.parametrize("category", ["project", "work", "research"])
def test_bert_uses_supported_labels_and_competency_without_double_counting(
    category,
) -> None:
    result = bert_result(category=category)
    profile = confirm(result)
    (evidence,) = mapped(profile)
    assert evidence.quality == "evaluated_outcome"
    assert evidence.depth == "designed_or_investigated"
    assert evidence.state == EvidenceState.SELF_REPORTED_PRESENT
    trace = evidence.qualitative_mapping
    assert trace.judgment_ids == ["depth", "evaluation", "impact"]
    assert trace.competency_suggestion_ids == ["ML"]
    assert trace.provisional and trace.version == "qualitative-mappings-v2"
    assert trace.rubric_sha256 == result.audit.rubric_sha256
    assert evidence.source_claim_id == "c1" and BERT in evidence.source
    assert "NLP" in result.supported_competency_ids  # no invented catalog node
    assert all(
        j.label == "unknown"
        for j in result.draft.judgments
        if j.dimension == "ownership"
    )
    assert confirm(result, profile=profile) == profile
    taxonomy = load_taxonomy()
    reversed_taxonomy = taxonomy.model_copy(
        update={"qualitative_mappings": tuple(reversed(taxonomy.qualitative_mappings))}
    )
    assert confirm(result, reversed_taxonomy) == profile
    ml = next(
        c
        for c in resolve_competencies(profile, taxonomy, as_of=AS_OF)
        if c.competency_id == "machine_learning"
    )
    assert len(ml.explanation_trace) == 1
    assert ml.explanation_trace[0].contribution == Decimal("2.4000")


def test_publication_metadata_preserved_without_venue_or_depth_invention() -> None:
    result = qualitative_result(PUBLICATION, category="publication")
    profile = confirm(result)
    assert not mapped(profile)
    (claim,) = profile.evidence
    assert claim.kind == "publication" and claim.raw_text == PUBLICATION
    assert claim.quality is None and claim.depth is None
    assert claim.state == EvidenceState.SELF_REPORTED_PRESENT
    assert result.questions  # authorship/topic alone establishes no method depth
    assert not result.supported_judgment_ids
    assert not result.supported_competency_ids
    assert (
        not {"venue_tier", "citation_count", "peer_reviewed"}
        & claim.model_dump().keys()
    )


def test_publication_with_described_method_scores_intrinsically_and_replays() -> None:
    result = qualitative_result(
        PUBLICATION + " Investigated segmentation errors using controlled ablations "
        "and compared transformer baselines; measured a 4-point Dice improvement.",
        category="publication",
        labels={
            "depth": "investigated",
            "evaluation": "compared",
            "impact": "measured",
        },
        skills={"segmentation investigation": "machine_learning"},
    )
    profile = confirm(result)
    (evidence,) = mapped(profile)
    assert evidence.quality == "evaluated_outcome"
    assert evidence.kind == "qualitative_machine_learning_activity"
    assert "Journal XYZ" in evidence.source
    taxonomy = load_taxonomy()
    rule = next(
        r
        for r in taxonomy.evidence_rules
        if r.id == evidence.qualitative_mapping.evidence_rule_id
    )
    config = load_evidence_configuration(taxonomy.evidence_configuration)
    self_reported = evaluate_evidence(evidence, rule, config, as_of=AS_OF)
    verified = evaluate_evidence(
        evidence.model_copy(update={"state": EvidenceState.VERIFIED_PRESENT}),
        rule,
        config,
        as_of=AS_OF,
    )
    assert verified.verification > self_reported.verification
    assert verified.raw_contribution > self_reported.raw_contribution
    assert evidence.state == EvidenceState.SELF_REPORTED_PRESENT
    assert_replay(profile, taxonomy)


def assert_replay(profile: StudentProfile, taxonomy: Taxonomy) -> None:
    program = load_program_config(Path(__file__).parent / "fixtures/cli/program.yaml")
    assessment = create_audited_assessment(
        profile,
        program,
        taxonomy=taxonomy,
        scoring_configuration=load_scoring_configuration(),
        as_of=AS_OF,
        timestamp=datetime(2026, 9, 11),
        engine_version="bridge-test",
    )
    assert assessment.audit.evidence_ids_used
    assert assessment.program_alignment.readiness_value is not None
    assert (
        replay_assessment(assessment).model_dump_json() == assessment.model_dump_json()
    )


def test_project_flows_through_existing_scoring_and_audit() -> None:
    assert_replay(confirm(bert_result()), load_taxonomy())


def test_team_ownership_is_rejected_even_if_student_confirms_it() -> None:
    result = qualitative_result(
        "Our team built a recommendation system.",
        attribution="team",
        labels={"ownership": "led", "depth": "applied"},
        skills={"ML": "machine_learning"},
        rejected=("ownership",),
    )
    assert "ownership" not in result.supported_judgment_ids
    assert not result.supported_competency_ids
    assert result.questions
    assert not mapped(confirm(result))


def test_vague_work_stays_unknown_and_requests_clarification() -> None:
    result = qualitative_result("Worked on machine learning projects.")
    assert all(j.label == "unknown" for j in result.draft.judgments)
    assert result.questions and "personally" in result.questions[0].question
    profile = confirm(result)
    assert not mapped(profile)
    assert all(
        c.state == EvidenceState.UNKNOWN
        for c in resolve_competencies(profile, load_taxonomy(), as_of=AS_OF)
    )


@pytest.mark.parametrize(
    "rejected, expected",
    [
        ("depth", None),
        ("ML", None),
        ("c1", None),
        ("impact", "substantive"),
        ("evaluation", "substantive"),
    ],
)
def test_unsupported_targets_never_activate_mapping(rejected, expected) -> None:
    evidence = mapped(confirm(bert_result(rejected=(rejected,))))
    assert [e.quality for e in evidence] == ([] if expected is None else [expected])


@pytest.mark.parametrize("decision", [ClaimDecision.EXCLUDE, ClaimDecision.UNCERTAIN])
def test_student_rejection_removes_mapping_on_reconfirmation(decision) -> None:
    result = bert_result()
    profile = confirm(result)
    changes = initial_judgment_corrections(result)
    changes = [
        j.model_copy(update={"decision": decision}) if j.judgment_id == "depth" else j
        for j in changes
    ]
    corrected = confirm_understanding(
        profile, result, initial_claim_corrections(result), [], changes, load_taxonomy()
    )
    assert not mapped(corrected)


def test_rubric_mismatch_fails_closed() -> None:
    taxonomy = load_taxonomy()
    changed = taxonomy.model_copy(
        update={
            "qualitative_mappings": tuple(
                m.model_copy(update={"rubric_sha256": "0" * 64})
                for m in taxonomy.qualitative_mappings
            )
        }
    )
    assert not mapped(confirm(bert_result(), changed))


def test_no_cross_competency_fanout_from_same_kind() -> None:
    taxonomy = load_taxonomy()
    profile = confirm(bert_result())
    rule = taxonomy.evidence_rules[-1].model_copy(
        update={"id": "unreviewed-fanout", "competency_id": "statistics"}
    )
    altered = taxonomy.model_copy(
        update={"evidence_rules": (*taxonomy.evidence_rules, rule)}
    )
    competencies = resolve_competencies(profile, altered, as_of=AS_OF)
    assert (
        next(c for c in competencies if c.competency_id == "statistics").state
        == EvidenceState.UNKNOWN
    )


def test_reconfirmation_replaces_old_mappings_after_configuration_change() -> None:
    result = bert_result()
    profile = confirm(result)
    taxonomy = load_taxonomy()
    changed = taxonomy.model_copy(
        update={
            "version": "test-new-content-hash",
            "qualitative_mapping_version": "test-v3",
            "qualitative_mappings": tuple(
                m
                for m in taxonomy.qualitative_mappings
                if m.quality_label != "evaluated_outcome"
            ),
        }
    )
    updated = confirm(result, changed, profile)
    (evidence,) = mapped(updated)
    assert evidence.quality == "substantive"
    assert evidence.qualitative_mapping.version == "test-v3"
    assert evidence.qualitative_mapping.taxonomy_version == "test-new-content-hash"
    assert mapped(profile)[0].id not in {item.id for item in updated.evidence}


def test_supported_duplicate_is_suppressed_before_mapping() -> None:
    from unihive.understanding import DuplicateGroup, SupportCheck, supported_ids

    result = bert_result()
    duplicate = result.draft.claims[0].model_copy(update={"id": "c2"})
    duplicate_judgments = [
        item.model_copy(update={"id": item.id + "-copy", "claim_id": "c2"})
        for item in result.draft.judgments
    ]
    duplicate_skills = [
        item.model_copy(update={"id": item.id + "-copy", "claim_id": "c2"})
        for item in result.draft.competencies
    ]
    draft = result.draft.model_copy(
        update={
            "claims": [*result.draft.claims, duplicate],
            "judgments": [*result.draft.judgments, *duplicate_judgments],
            "competencies": [*result.draft.competencies, *duplicate_skills],
        }
    )
    review = result.support_review.model_copy(
        update={
            "checks": [
                *result.support_review.checks,
                *[
                    SupportCheck(
                        target_id=item.id,
                        verdict="supported",
                        explanation="Repeated source wording.",
                    )
                    for item in [duplicate, *duplicate_judgments, *duplicate_skills]
                ],
            ],
            "duplicate_groups": [
                DuplicateGroup(
                    canonical_claim_id="c1",
                    duplicate_claim_ids=["c2"],
                    explanation="Same classifier.",
                )
            ],
        }
    )
    claims, judgments, skills = supported_ids(draft, review)
    repeated = result.model_copy(
        update={
            "draft": draft,
            "support_review": review,
            "supported_claim_ids": claims,
            "supported_judgment_ids": judgments,
            "supported_competency_ids": skills,
        }
    )
    assert len(mapped(confirm(repeated))) == 1
