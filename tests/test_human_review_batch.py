"""Stage 4C manifest checks keep human adjudication separate from seed data."""

import pytest

from qa.human_review_batch import (
    BATCH_PATH,
    immutable_record_digest,
    load_review_batch,
    validate_review_batch,
)
from qa.human_review_dataset import load_dataset


def test_stage4c_batch_is_reference_only_and_pending():
    manifest = load_review_batch(BATCH_PATH)
    records = {record.review_id: record for record in load_dataset()}
    assert 20 <= len(manifest.cases) <= 30
    assert len({case.review_id for case in manifest.cases}) == len(manifest.cases)
    assert all(
        records[case.review_id].human_review.status == "pending"
        for case in manifest.cases
    )
    assert all(
        records[case.review_id].human_review.final_label is None
        for case in manifest.cases
    )
    assert all(case.review_id in records for case in manifest.cases)


def test_stage4c_manifest_matches_canonical_domain_lineage_and_integrity():
    manifest = load_review_batch(BATCH_PATH)
    records = load_dataset()
    by_id = {record.review_id: record for record in records}
    for case in manifest.cases:
        record = by_id[case.review_id]
        assert case.review_domain == record.review_domain
        assert case.lineage_group == record.leakage_control.lineage_group
        assert case.source_fingerprint == record.leakage_control.source_fingerprint
        assert case.immutable_record_sha256 == immutable_record_digest(record)


def test_stage4c_rejects_a_changed_canonical_record():
    manifest = load_review_batch(BATCH_PATH)
    records = load_dataset()
    selected_id = manifest.cases[0].review_id
    original = next(record for record in records if record.review_id == selected_id)
    changed = original.model_copy(
        update={"source": original.source.model_copy(update={"text": "changed"})}
    )
    changed_records = [
        changed if record.review_id == selected_id else record for record in records
    ]
    with pytest.raises(ValueError, match="Canonical record changed"):
        validate_review_batch(manifest, changed_records)


def test_stage4c_rejects_non_pending_selection():
    manifest = load_review_batch(BATCH_PATH)
    records = load_dataset()
    selected_id = manifest.cases[0].review_id
    changed = next(
        record.model_copy(
            update={
                "human_review": record.human_review.model_copy(
                    update={"status": "adjudicated"}
                )
            }
        )
        for record in records
        if record.review_id == selected_id
    )
    changed_records = [
        changed if record.review_id == selected_id else record for record in records
    ]
    with pytest.raises(ValueError, match="Selected case is no longer pending"):
        validate_review_batch(manifest, changed_records)


def test_stage4c_rejects_an_unknown_review_id():
    manifest = load_review_batch(BATCH_PATH)
    records = load_dataset()
    item = manifest.cases[0].model_copy(update={"review_id": "missing-review-id"})
    changed_manifest = manifest.model_copy(
        update={"cases": [item, *manifest.cases[1:]]}
    )
    with pytest.raises(ValueError, match="Unknown review ID"):
        validate_review_batch(changed_manifest, records)
