"""Seed and validate the Stage 4 manual-adjudication dataset.

The dataset stores model output as a review input only.  This module never copies
either a provisional reference or a model prediction into ``human_review``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from qa.cross_domain_evidence import GoldenCase, GoldenSuite
from unihive.models import CoreModel
from unihive.taxonomy import Taxonomy, load_taxonomy
from unihive.understanding import (
    SourceDocument,
    SupportReview,
    UnderstandingDraft,
    UnderstandingResult,
    load_evaluation_rubric,
    supported_context_ids,
    supported_ids,
    validate_draft,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "qa/human_review_cases.jsonl"
SCHEMA_VERSION = "human-review-v1"
FORBIDDEN_SCORING_KEYS = {
    "admission_probability",
    "overall_score",
    "probability",
    "readiness",
    "score",
    "scores",
    "weight",
    "weights",
}


class SeedSpec(CoreModel):
    review_id: str
    review_domain: str
    fixture_path: str
    fixture_case_id: str
    model_artifact_path: str | None
    lineage_group: str


SEEDS = (
    SeedSpec(
        review_id="hr-computer-science-programming",
        review_domain="computer_science",
        fixture_path="tests/fixtures/understanding/context_presence_golden.json",
        fixture_case_id="context-programming-project",
        model_artifact_path=(
            "data/reviews/context-v7-live-01/context-programming-project.json"
        ),
        lineage_group="programming_evidence",
    ),
    SeedSpec(
        review_id="hr-machine-learning-evaluation",
        review_domain="machine_learning",
        fixture_path="tests/fixtures/understanding/cross_domain_golden.json",
        fixture_case_id="ml-deep",
        model_artifact_path="data/reviews/cross-domain-live-v5-01/ml-deep.json",
        lineage_group="machine_learning_evidence",
    ),
    SeedSpec(
        review_id="hr-cybersecurity-packet-analysis",
        review_domain="cybersecurity",
        fixture_path="tests/fixtures/understanding/cross_domain_golden.json",
        fixture_case_id="cyber-basic",
        model_artifact_path="data/reviews/cross-domain-live-v5-01/cyber-basic.json",
        lineage_group="network_security_evidence",
    ),
    SeedSpec(
        review_id="hr-civil-structural-design",
        review_domain="civil",
        fixture_path="tests/fixtures/understanding/cross_domain_golden.json",
        fixture_case_id="civil-deep",
        model_artifact_path="data/reviews/cross-domain-live-smoke-01/civil-deep.json",
        lineage_group="structural_engineering_evidence",
    ),
    SeedSpec(
        review_id="hr-mechanical-simulation",
        review_domain="mechanical",
        fixture_path="tests/fixtures/understanding/semantic_reliability.json",
        fixture_case_id="mixed-mechanical-matlab",
        model_artifact_path=None,
        lineage_group="mechanical_simulation_evidence",
    ),
    SeedSpec(
        review_id="hr-electrical-embedded-design",
        review_domain="electrical_embedded",
        fixture_path="tests/fixtures/understanding/semantic_reliability.json",
        fixture_case_id="tool-verilog-activity",
        model_artifact_path=None,
        lineage_group="embedded_digital_systems_evidence",
    ),
    SeedSpec(
        review_id="hr-qualitative-research",
        review_domain="research",
        fixture_path="tests/fixtures/understanding/cross_domain_golden.json",
        fixture_case_id="neutral-research-absence",
        model_artifact_path=(
            "data/reviews/cross-domain-live-v5-01/neutral-research-absence.json"
        ),
        lineage_group="qualitative_research_evidence",
    ),
    SeedSpec(
        review_id="hr-teaching-instruction",
        review_domain="teaching",
        fixture_path="tests/fixtures/understanding/cross_domain_golden.json",
        fixture_case_id="neutral-teaching",
        model_artifact_path=None,
        lineage_group="teaching_instruction_evidence",
    ),
)


class SourceProvenance(CoreModel):
    fixture_path: str
    fixture_case_id: str
    document_id: Literal["source"]
    text: str = Field(min_length=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewLabel(CoreModel):
    understanding: UnderstandingDraft
    support_review: SupportReview
    demonstrated_methods: list[str]


class ProvisionalReference(CoreModel):
    status: Literal["provisional"]
    annotation_status: str = Field(min_length=1)
    label: ReviewLabel


class ModelPrediction(CoreModel):
    status: Literal["available", "not_available"]
    artifact_path: str | None
    artifact_sha256: str | None
    label_sha256: str | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    label: ReviewLabel | None
    unavailable_reason: str | None

    @model_validator(mode="after")
    def validate_availability(self) -> ModelPrediction:
        available = (
            self.artifact_path,
            self.artifact_sha256,
            self.label_sha256,
            self.provider,
            self.model,
            self.prompt_version,
            self.label,
        )
        if self.status == "available" and (
            any(value is None for value in available)
            or self.unavailable_reason is not None
        ):
            raise ValueError("Available predictions require an artifact and label")
        if self.status == "not_available" and (
            any(value is not None for value in available)
            or not self.unavailable_reason
        ):
            raise ValueError("Unavailable predictions require only a reason")
        return self


class UncertainField(CoreModel):
    source: Literal["provisional_reference", "model_prediction", "human_review"]
    field_path: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class DisputedField(CoreModel):
    field_path: str = Field(min_length=1)
    provisional_value: JsonValue | None
    model_value: JsonValue | None
    human_final_value: JsonValue | None
    resolution: Literal["open", "resolved"]
    note: str = Field(min_length=1)


class HumanReview(CoreModel):
    status: Literal["pending", "adjudicated"]
    reviewer_id: str | None
    reviewed_at: datetime | None
    final_label: ReviewLabel | None
    uncertain_fields: list[UncertainField]
    disputed_fields: list[DisputedField]
    notes: list[str]

    @model_validator(mode="after")
    def prevent_automatic_gold(self) -> HumanReview:
        if self.status == "pending" and any(
            value is not None
            for value in (self.reviewer_id, self.reviewed_at, self.final_label)
        ):
            raise ValueError("Pending records cannot contain a human final label")
        if self.status == "adjudicated" and any(
            value is None
            for value in (self.reviewer_id, self.reviewed_at, self.final_label)
        ):
            raise ValueError(
                "Adjudicated records require reviewer, timestamp, and final label"
            )
        if self.status == "adjudicated" and any(
            item.resolution == "open" for item in self.disputed_fields
        ):
            raise ValueError("Adjudicated records cannot retain open disputes")
        return self


class LeakageControl(CoreModel):
    lineage_group: str = Field(min_length=1)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: Literal["unassigned", "train", "validation", "test"]


class HumanReviewRecord(CoreModel):
    schema_version: Literal["human-review-v1"]
    review_id: str = Field(min_length=1)
    review_domain: str = Field(min_length=1)
    source: SourceProvenance
    provisional_reference: ProvisionalReference
    model_prediction: ModelPrediction
    human_review: HumanReview
    leakage_control: LeakageControl


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def canonical_digest(value: JsonValue) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return digest_bytes(encoded)


def validate_no_scoring_fields(value: JsonValue) -> None:
    """Keep numeric scoring contracts outside adjudication and tuning data."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower()
            if (
                normalized in FORBIDDEN_SCORING_KEYS
                or normalized.endswith("_score")
                or normalized.endswith("_weight")
            ):
                raise ValueError(f"Scoring field is forbidden in review data: {key}")
            validate_no_scoring_fields(item)
    elif isinstance(value, list):
        for item in value:
            validate_no_scoring_fields(item)


def repository_path(relative: str) -> Path:
    if "\\" in relative or Path(relative).is_absolute():
        raise ValueError("Dataset paths must be repository-relative POSIX paths")
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def load_fixture_case(relative: str, case_id: str) -> tuple[GoldenCase, str, str]:
    path = repository_path(relative)
    raw = path.read_bytes()
    payload = json.loads(raw)
    suite = GoldenSuite.model_validate(payload)
    matches = [
        case for case in [*suite.cases, *suite.probes] if case.id == case_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Fixture case reference is not unique: {relative}#{case_id}")
    raw_matches = [
        case
        for case in [*payload.get("cases", []), *payload.get("probes", [])]
        if case.get("id") == case_id
    ]
    if len(raw_matches) != 1:
        raise ValueError(f"Raw fixture case reference is not unique: {case_id}")
    return matches[0], digest_bytes(raw), canonical_digest(raw_matches[0])


def validate_label(
    label: ReviewLabel, source: SourceProvenance, taxonomy: Taxonomy
) -> None:
    validate_draft(
        label.understanding,
        [SourceDocument(id=source.document_id, text=source.text)],
        load_evaluation_rubric(),
        {node.id: node.description for node in taxonomy.competencies},
    )
    supported_ids(label.understanding, label.support_review)
    supported_context_ids(label.understanding, label.support_review)
    if len(label.demonstrated_methods) != len(set(label.demonstrated_methods)):
        raise ValueError("Demonstrated methods must be unique")
    if any(not method.strip() for method in label.demonstrated_methods):
        raise ValueError("Demonstrated methods must be nonblank")


def prediction_from_artifact(relative: str | None) -> ModelPrediction:
    if relative is None:
        return ModelPrediction(
            status="not_available",
            artifact_path=None,
            artifact_sha256=None,
            label_sha256=None,
            provider=None,
            model=None,
            prompt_version=None,
            label=None,
            unavailable_reason=(
                "No existing live-model artifact was recorded for this case."
            ),
        )
    path = repository_path(relative)
    raw = path.read_bytes()
    result = UnderstandingResult.model_validate_json(raw)
    label = ReviewLabel(
        understanding=result.draft,
        support_review=result.support_review,
        demonstrated_methods=list(
            dict.fromkeys(item.observed_skill for item in result.draft.competencies)
        ),
    )
    return ModelPrediction(
        status="available",
        artifact_path=relative,
        artifact_sha256=digest_bytes(raw),
        label_sha256=canonical_digest(label.model_dump(mode="json")),
        provider=result.audit.provider,
        model=result.audit.model,
        prompt_version=result.audit.prompt_version,
        label=label,
        unavailable_reason=None,
    )


def uncertainty_flags(
    label: ReviewLabel, source: Literal["provisional_reference", "model_prediction"]
) -> list[UncertainField]:
    flags = [
        UncertainField(
            source=source,
            field_path=(
                f"{source}.label.understanding.judgments"
                f"[{item.claim_id}:{item.dimension}].label"
            ),
            reason="The annotation explicitly leaves this rubric dimension unknown.",
        )
        for item in label.understanding.judgments
        if item.label == "unknown"
    ]
    flags.extend(
        UncertainField(
            source=source,
            field_path=f"{source}.label.understanding.questions[{index}]",
            reason=item.reason,
        )
        for index, item in enumerate(label.understanding.questions)
    )
    flags.extend(
        UncertainField(
            source=source,
            field_path=f"{source}.label.understanding.unassessed[{index}]",
            reason=item,
        )
        for index, item in enumerate(label.understanding.unassessed)
    )
    flags.extend(
        UncertainField(
            source=source,
            field_path=(
                f"{source}.label.support_review.checks[{item.target_id}].verdict"
            ),
            reason=item.explanation,
        )
        for item in label.support_review.checks
        if item.verdict.value == "uncertain"
    )
    return flags


def build_seed_record(spec: SeedSpec) -> HumanReviewRecord:
    case, fixture_digest, case_digest = load_fixture_case(
        spec.fixture_path, spec.fixture_case_id
    )
    source_digest = digest_bytes(case.source_text.encode("utf-8"))
    provisional_label = ReviewLabel(
        understanding=case.expected_understanding,
        support_review=case.expected_support_review,
        demonstrated_methods=case.semantic_context.methods_performed,
    )
    prediction = prediction_from_artifact(spec.model_artifact_path)
    flags = uncertainty_flags(provisional_label, "provisional_reference")
    if prediction.label is not None:
        flags.extend(uncertainty_flags(prediction.label, "model_prediction"))
    return HumanReviewRecord(
        schema_version=SCHEMA_VERSION,
        review_id=spec.review_id,
        review_domain=spec.review_domain,
        source=SourceProvenance(
            fixture_path=spec.fixture_path,
            fixture_case_id=spec.fixture_case_id,
            document_id="source",
            text=case.source_text,
            text_sha256=source_digest,
            fixture_sha256=fixture_digest,
            fixture_case_sha256=case_digest,
        ),
        provisional_reference=ProvisionalReference(
            status="provisional",
            annotation_status=case.annotation_status,
            label=provisional_label,
        ),
        model_prediction=prediction,
        human_review=HumanReview(
            status="pending",
            reviewer_id=None,
            reviewed_at=None,
            final_label=None,
            uncertain_fields=flags,
            disputed_fields=[],
            notes=[],
        ),
        leakage_control=LeakageControl(
            lineage_group=spec.lineage_group,
            source_fingerprint=source_digest,
            split="unassigned",
        ),
    )


def validate_record(record: HumanReviewRecord, taxonomy: Taxonomy) -> None:
    validate_no_scoring_fields(record.model_dump(mode="json"))
    case, fixture_digest, case_digest = load_fixture_case(
        record.source.fixture_path, record.source.fixture_case_id
    )
    if record.source.text != case.source_text:
        raise ValueError(f"Broken source text reference: {record.review_id}")
    if record.source.text_sha256 != digest_bytes(record.source.text.encode("utf-8")):
        raise ValueError(f"Broken source text digest: {record.review_id}")
    if record.source.fixture_sha256 != fixture_digest:
        raise ValueError(f"Changed fixture file: {record.review_id}")
    if record.source.fixture_case_sha256 != case_digest:
        raise ValueError(f"Changed fixture case: {record.review_id}")
    expected = ReviewLabel(
        understanding=case.expected_understanding,
        support_review=case.expected_support_review,
        demonstrated_methods=case.semantic_context.methods_performed,
    )
    if record.provisional_reference.annotation_status != case.annotation_status:
        raise ValueError(f"Changed annotation status: {record.review_id}")
    if record.provisional_reference.label != expected:
        raise ValueError(f"Changed provisional reference: {record.review_id}")
    validate_label(record.provisional_reference.label, record.source, taxonomy)

    prediction = record.model_prediction
    if prediction.status == "available":
        assert prediction.artifact_path is not None
        assert prediction.artifact_sha256 is not None
        assert prediction.label_sha256 is not None
        assert prediction.label is not None
        if prediction.label_sha256 != canonical_digest(
            prediction.label.model_dump(mode="json")
        ):
            raise ValueError(f"Changed model prediction snapshot: {record.review_id}")
        validate_label(prediction.label, record.source, taxonomy)
        artifact = repository_path(prediction.artifact_path)
        if artifact.exists():
            raw = artifact.read_bytes()
            if prediction.artifact_sha256 != digest_bytes(raw):
                raise ValueError(f"Changed model artifact: {record.review_id}")
            expected_prediction = prediction_from_artifact(
                prediction.artifact_path
            )
            if prediction != expected_prediction:
                raise ValueError(
                    f"Changed model prediction snapshot: {record.review_id}"
                )
            result = UnderstandingResult.model_validate_json(raw)
            documents = {item.id: item.text for item in result.documents}
            if documents != {record.source.document_id: record.source.text}:
                raise ValueError(
                    f"Model artifact uses a different source: {record.review_id}"
                )

    if record.human_review.final_label is not None:
        validate_label(record.human_review.final_label, record.source, taxonomy)
    if record.leakage_control.source_fingerprint != record.source.text_sha256:
        raise ValueError(f"Incorrect leakage fingerprint: {record.review_id}")


def load_dataset(path: Path = DATASET_PATH) -> list[HumanReviewRecord]:
    records = [
        HumanReviewRecord.model_validate_json(line)
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]
    ids = [record.review_id for record in records]
    if not records or len(ids) != len(set(ids)):
        raise ValueError("Review IDs must be nonempty and unique")
    taxonomy = load_taxonomy()
    for record in records:
        validate_record(record, taxonomy)
    for grouping in ("source_fingerprint", "lineage_group"):
        splits_by_group: dict[str, set[str]] = {}
        for record in records:
            group = getattr(record.leakage_control, grouping)
            splits_by_group.setdefault(group, set()).add(
                record.leakage_control.split
            )
        if any(len(splits - {"unassigned"}) > 1 for splits in splits_by_group.values()):
            raise ValueError(f"Leakage group crosses assigned splits: {grouping}")
    return records


def seed_jsonl() -> str:
    return "".join(
        json.dumps(record.model_dump(mode="json"), separators=(",", ":")) + "\n"
        for record in map(build_seed_record, SEEDS)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-seed",
        action="store_true",
        help=(
            "Replace the dataset with pending seed records; never creates gold labels."
        ),
    )
    args = parser.parse_args()
    if args.write_seed:
        DATASET_PATH.write_text(seed_jsonl(), "utf-8")
    records = load_dataset()
    print(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "records": len(records),
                "pending": sum(
                    record.human_review.status == "pending" for record in records
                ),
                "adjudicated": sum(
                    record.human_review.status == "adjudicated"
                    for record in records
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
