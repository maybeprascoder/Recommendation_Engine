"""Validate the compact Stage 4C human-review batch manifest."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue

from qa.human_review_dataset import (
    DATASET_PATH,
    HumanReviewRecord,
    load_dataset,
    validate_no_scoring_fields,
)
from unihive.models import CoreModel

ROOT = Path(__file__).resolve().parents[1]
BATCH_PATH = ROOT / "qa/human_review_batch_stage4c.json"
SCHEMA_VERSION = "human-review-batch-v1"
FORBIDDEN_LABEL_TERMS = {"safe", "moderate", "ambitious"}


class ReviewBatchCase(CoreModel):
    review_id: str = Field(min_length=1)
    review_domain: str = Field(min_length=1)
    lineage_group: str = Field(min_length=1)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    immutable_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_focus: list[str] = Field(min_length=1)


class ReviewBatchManifest(CoreModel):
    schema_version: Literal["human-review-batch-v1"]
    batch_id: str = Field(min_length=1)
    dataset_path: Literal["qa/human_review_cases.jsonl"]
    cases: list[ReviewBatchCase]


def canonical_digest(value: JsonValue) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def immutable_record_digest(record: HumanReviewRecord) -> str:
    """Hash immutable blocks while the human review fields stay editable."""
    payload = {
        "source": record.source.model_dump(mode="json"),
        "provisional_reference": record.provisional_reference.model_dump(mode="json"),
        "model_prediction": record.model_prediction.model_dump(mode="json"),
        "leakage_control": record.leakage_control.model_dump(mode="json"),
    }
    return canonical_digest(payload)


def _contains_forbidden_label(value: JsonValue, parent_key: str = "") -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = key.lower()
            if normalized_key in {
                "admission_probability",
                "admission_score",
                "program_fit",
                "program_fit_score",
                "university_relevance",
                "scoring_weight",
                "scoring_weights",
            }:
                return True
            if _contains_forbidden_label(item, normalized_key):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_label(item, parent_key) for item in value)
    elif isinstance(value, str) and parent_key in {"label", "band", "category"}:
        return value.lower() in FORBIDDEN_LABEL_TERMS
    return False


def validate_review_batch(
    manifest: ReviewBatchManifest, records: list[HumanReviewRecord]
) -> None:
    """Validate manifest references without promoting or mutating dataset records."""
    if not 20 <= len(manifest.cases) <= 30:
        raise ValueError("Stage 4C review batch must contain between 20 and 30 cases")
    ids = [item.review_id for item in manifest.cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Stage 4C review batch IDs must be unique")
    by_id = {record.review_id: record for record in records}
    if len(by_id) != len(records):
        raise ValueError("Canonical dataset review IDs must be unique")
    for item in manifest.cases:
        record = by_id.get(item.review_id)
        if record is None:
            raise ValueError(f"Unknown review ID in Stage 4C batch: {item.review_id}")
        if item.review_domain != record.review_domain:
            raise ValueError(f"Domain mismatch for Stage 4C case: {item.review_id}")
        if item.lineage_group != record.leakage_control.lineage_group:
            raise ValueError(f"Lineage mismatch for Stage 4C case: {item.review_id}")
        if item.source_fingerprint != record.leakage_control.source_fingerprint:
            raise ValueError(f"Source fingerprint mismatch: {item.review_id}")
        if item.immutable_record_sha256 != immutable_record_digest(record):
            raise ValueError(f"Canonical record changed: {item.review_id}")
        if record.human_review.status != "pending":
            raise ValueError(
                f"Selected case is no longer pending: {item.review_id}"
            )
        if record.human_review.final_label is not None:
            raise ValueError(
                f"Selected case already has a final label: {item.review_id}"
            )
        payload = record.model_dump(mode="json")
        validate_no_scoring_fields(payload)
        if _contains_forbidden_label(payload):
            raise ValueError(
                f"Scoring or admissions label in selected case: {item.review_id}"
            )
    validate_no_scoring_fields(manifest.model_dump(mode="json"))


def load_review_batch(
    path: Path = BATCH_PATH, dataset_path: Path = DATASET_PATH
) -> ReviewBatchManifest:
    manifest = ReviewBatchManifest.model_validate_json(path.read_text("utf-8"))
    records = load_dataset(dataset_path)
    validate_review_batch(manifest, records)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Stage 4C review batch")
    parser.add_argument("--manifest", type=Path, default=BATCH_PATH)
    args = parser.parse_args()
    manifest = load_review_batch(args.manifest)
    domains: dict[str, int] = {}
    for case in manifest.cases:
        domains[case.review_domain] = domains.get(case.review_domain, 0) + 1
    print(
        json.dumps(
            {
                "batch_id": manifest.batch_id,
                "cases": len(manifest.cases),
                "domains": domains,
                "status": "pending_only",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
