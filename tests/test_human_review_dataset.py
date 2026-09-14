"""Stage 4 human-adjudication records remain provisional and source-exact."""

from datetime import UTC, datetime

import pytest

from qa.human_review_dataset import (
    DATASET_PATH,
    SEEDS,
    HumanReview,
    ReviewLabel,
    build_seed_record,
    load_dataset,
    validate_no_scoring_fields,
    validate_record,
)
from unihive.taxonomy import load_taxonomy


def nested_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from nested_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_keys(item)


def test_provisional_dataset_is_ready_but_has_no_gold_labels():
    records = load_dataset(DATASET_PATH)
    assert len(records) == 100
    assert {
        domain: sum(record.review_domain == domain for record in records)
        for domain in {record.review_domain for record in records}
    } == {
        "computer_science": 12,
        "machine_learning": 12,
        "cybersecurity": 12,
        "civil": 12,
        "mechanical": 10,
        "electrical_embedded": 10,
        "research": 10,
        "teaching": 6,
        "interdisciplinary": 8,
        "semantic_traps": 8,
    }
    assert sum(record.model_prediction.status == "available" for record in records) == 5
    assert all(record.human_review.status == "pending" for record in records)
    assert all(record.human_review.final_label is None for record in records)
    assert all(record.leakage_control.split == "unassigned" for record in records)
    assert all(record.human_review.uncertain_fields for record in records)


def test_seed_builder_never_promotes_a_reference_or_prediction_to_gold():
    spec = next(spec for spec in SEEDS if spec.model_artifact_path is None)
    record = build_seed_record(spec)
    assert record.human_review == HumanReview(
        status="pending",
        reviewer_id=None,
        reviewed_at=None,
        final_label=None,
        uncertain_fields=record.human_review.uncertain_fields,
        disputed_fields=[],
        notes=[],
    )


def test_dataset_contract_has_no_numeric_scoring_fields():
    forbidden = {
        "score",
        "scores",
        "weight",
        "weights",
        "readiness",
        "admission_probability",
    }
    for record in load_dataset(DATASET_PATH):
        assert forbidden.isdisjoint(nested_keys(record.model_dump(mode="json")))


def test_validator_rejects_scoring_fields_inside_dispute_values():
    with pytest.raises(ValueError, match="Scoring field is forbidden"):
        validate_no_scoring_fields({"candidate": {"overall_score": 0.8}})


def test_changed_source_text_is_rejected():
    record = load_dataset(DATASET_PATH)[0]
    changed_source = record.source.model_copy(update={"text": record.source.text + " "})
    changed = record.model_copy(update={"source": changed_source})
    with pytest.raises(ValueError, match="Broken source text reference"):
        validate_record(changed, load_taxonomy())


def test_invalid_human_rubric_label_is_rejected():
    record = load_dataset(DATASET_PATH)[0]
    payload = record.provisional_reference.label.model_dump(mode="json")
    payload["understanding"]["judgments"][0]["label"] = "expert"
    final_label = ReviewLabel.model_validate(payload)
    human_review = HumanReview(
        status="adjudicated",
        reviewer_id="reviewer-example",
        reviewed_at=datetime(2026, 9, 14, tzinfo=UTC),
        final_label=final_label,
        uncertain_fields=record.human_review.uncertain_fields,
        disputed_fields=[],
        notes=["Test-only invalid label."],
    )
    changed = record.model_copy(update={"human_review": human_review})
    with pytest.raises(
        ValueError, match="Judgment uses an unknown rubric dimension or label"
    ):
        validate_record(changed, load_taxonomy())


def test_adjudicated_records_require_a_named_reviewer_and_final_label():
    with pytest.raises(ValueError, match="Adjudicated records require"):
        HumanReview(
            status="adjudicated",
            reviewer_id=None,
            reviewed_at=None,
            final_label=None,
            uncertain_fields=[],
            disputed_fields=[],
            notes=[],
        )
