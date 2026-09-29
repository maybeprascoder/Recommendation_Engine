"""Run local-model diagnostics over canonical human-review cases.

This is a comparison against provisional references for investigation. It does
not produce gold labels, accuracy scores, dataset splits, or scoring inputs.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import JsonValue

from qa.human_review_batch import BATCH_PATH, load_review_batch
from qa.human_review_dataset import (
    DATASET_PATH,
    HumanReviewRecord,
    ReviewLabel,
    load_dataset,
)
from unihive.llm.provider import (
    CompatibleChatClient,
    Completion,
    ProviderError,
    StructuredClient,
)
from unihive.llm.understanding import analyze_documents
from unihive.models import CoreModel
from unihive.taxonomy import load_taxonomy
from unihive.understanding import (
    SourceDocument,
    UnderstandingDraft,
    UnderstandingResult,
    supported_context_ids,
    supported_ids,
)

EXPECTED_MODEL = "qwen3.5:9b"
REPOSITORY_ROOT = DATASET_PATH.parent.parent


class CapturedCall(CoreModel):
    name: str
    prompt_version: str | None
    status: Literal["completed", "provider_error"]
    seconds: float
    instructions_sha256: str
    payload_sha256: str
    schema_sha256: str
    response_id: str | None
    model: str | None
    text: str | None
    error: str | None


class DiagnosticClient:
    """Capture exact local completions and request fingerprints per case."""

    def __init__(self, inner: StructuredClient) -> None:
        self._inner = inner
        self.provider = inner.provider
        self.model = inner.model
        self.calls: list[CapturedCall] = []

    def complete(
        self,
        *,
        instructions: str,
        payload: str,
        schema: dict[str, JsonValue],
        name: str,
    ) -> Completion:
        started = perf_counter()
        completion: Completion | None = None
        error: str | None = None
        try:
            completion = self._inner.complete(
                instructions=instructions,
                payload=payload,
                schema=schema,
                name=name,
            )
            return completion
        except ProviderError as exc:
            error = str(exc)
            raise
        finally:
            self.calls.append(
                CapturedCall(
                    name=name,
                    prompt_version=_prompt_version(instructions),
                    status="completed" if completion is not None else "provider_error",
                    seconds=round(perf_counter() - started, 2),
                    instructions_sha256=_text_digest(instructions),
                    payload_sha256=_text_digest(payload),
                    schema_sha256=_canonical_digest(schema),
                    response_id=(
                        completion.response_id if completion is not None else None
                    ),
                    model=completion.model if completion is not None else None,
                    text=completion.text if completion is not None else None,
                    error=error,
                )
            )


class DiagnosticDifference(CoreModel):
    field: str
    provisional_reference: JsonValue
    model_prediction: JsonValue
    question: str


class SemanticSnapshot(CoreModel):
    claims: list[dict[str, str]]
    contexts: list[dict[str, str]]
    demonstrated_methods: list[str]
    competency_suggestions: list[dict[str, str | None]]
    judgments: dict[str, list[str]]
    unknowns: list[str]
    explicit_absence: list[str]
    questions: list[str]
    unassessed: list[str]


def _text_digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _prompt_version(instructions: str) -> str | None:
    first_line = instructions.splitlines()[0].strip() if instructions else ""
    prefix = "version:"
    if not first_line.casefold().startswith(prefix):
        return None
    version = first_line[len(prefix) :].strip()
    return version or None


def _canonical_digest(value: JsonValue) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _provenance_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _snapshot(
    draft: UnderstandingDraft,
    claim_ids: list[str],
    judgment_ids: list[str],
    competency_ids: list[str],
    context_ids: list[str],
    demonstrated_methods: list[str],
    questions: list[str],
    unassessed: list[str],
) -> SemanticSnapshot:
    claims = sorted(
        (
            {
                "statement": item.statement,
                "category": item.category.value,
                "attribution": item.attribution.value,
                "presence": item.presence.value,
            }
            for item in draft.claims
            if item.id in claim_ids
        ),
        key=lambda item: json.dumps(item, sort_keys=True),
    )
    contexts = sorted(
        (
            {"kind": item.kind.value, "label": item.label}
            for item in draft.contexts
            if item.id in context_ids
        ),
        key=lambda item: (item["kind"], item["label"].casefold()),
    )
    suggestions = sorted(
        (
            {
                "competency_id": item.competency_id,
                "observed_skill": item.observed_skill,
            }
            for item in draft.competencies
            if item.id in competency_ids
        ),
        key=lambda item: (
            item["competency_id"] or "",
            item["observed_skill"].casefold(),
        ),
    )
    judgments: dict[str, list[str]] = {}
    for item in draft.judgments:
        if item.id in judgment_ids:
            judgments.setdefault(item.dimension, []).append(item.label)
    judgments = {
        dimension: sorted(labels)
        for dimension, labels in sorted(judgments.items())
    }
    unknowns = sorted(
        [
            f"judgment:{item.dimension}"
            for item in draft.judgments
            if item.id in judgment_ids and item.label == "unknown"
        ]
        + [
            "claim_presence"
            for item in draft.claims
            if item.id in claim_ids and item.presence.value == "unknown"
        ]
    )
    explicit_absence = sorted(
        item.statement
        for item in draft.claims
        if item.id in claim_ids and item.presence.value == "reported_absent"
    )
    return SemanticSnapshot(
        claims=claims,
        contexts=contexts,
        demonstrated_methods=sorted(set(demonstrated_methods)),
        competency_suggestions=suggestions,
        judgments=judgments,
        unknowns=unknowns,
        explicit_absence=explicit_absence,
        questions=sorted(questions),
        unassessed=sorted(unassessed),
    )


def provisional_snapshot(label: ReviewLabel) -> SemanticSnapshot:
    claim_ids, judgment_ids, competency_ids = supported_ids(
        label.understanding, label.support_review
    )
    return _snapshot(
        label.understanding,
        claim_ids,
        judgment_ids,
        competency_ids,
        supported_context_ids(label.understanding, label.support_review),
        label.demonstrated_methods,
        [item.question for item in label.understanding.questions],
        label.understanding.unassessed,
    )


def model_snapshot(result: UnderstandingResult) -> SemanticSnapshot:
    methods = [
        item.observed_skill
        for item in result.draft.competencies
        if item.id in result.supported_competency_ids
    ]
    return _snapshot(
        result.draft,
        result.supported_claim_ids,
        result.supported_judgment_ids,
        result.supported_competency_ids,
        result.supported_context_ids,
        methods,
        [item.question for item in result.questions],
        result.draft.unassessed,
    )


def compare_snapshots(
    reference: SemanticSnapshot, prediction: SemanticSnapshot
) -> list[DiagnosticDifference]:
    questions = {
        "claims": "Does either claim segmentation or wording exceed the source?",
        "contexts": (
            "Which cited tools, domains, or concepts should remain context only?"
        ),
        "demonstrated_methods": "Which performed methods are explicitly supported?",
        "competency_suggestions": (
            "Which competency routes are supported without inference?"
        ),
        "judgments": (
            "Which ownership, depth, evaluation, or impact labels does the source "
            "support?"
        ),
        "unknowns": (
            "Should uncertainty remain, or does the source support a stronger label?"
        ),
        "explicit_absence": "Is each absence explicit and narrowly scoped?",
        "questions": "Which clarification questions are still needed?",
        "unassessed": "Which source limitations must remain unassessed?",
    }
    differences = []
    reference_payload = reference.model_dump(mode="json")
    prediction_payload = prediction.model_dump(mode="json")
    for field, question in questions.items():
        if reference_payload[field] != prediction_payload[field]:
            differences.append(
                DiagnosticDifference(
                    field=field,
                    provisional_reference=reference_payload[field],
                    model_prediction=prediction_payload[field],
                    question=question,
                )
            )
    return differences


def classify_failure(error: str, calls: list[CapturedCall]) -> str:
    if "Support review failed" in error:
        return "support_review_validation"
    if "Interpretation" in error:
        return "understanding_parse_or_validation"
    if calls and calls[-1].status == "provider_error":
        return f"provider_{calls[-1].name}"
    return "pipeline_validation"


def select_records(
    records: list[HumanReviewRecord],
    manifest_ids: list[str],
    selection: Literal["manifest", "remaining", "all"],
) -> list[HumanReviewRecord]:
    by_id = {record.review_id: record for record in records}
    manifest = [by_id[review_id] for review_id in manifest_ids]
    remaining = [record for record in records if record.review_id not in manifest_ids]
    if selection == "manifest":
        return manifest
    if selection == "remaining":
        return remaining
    return [*manifest, *remaining]


def _write_json(path: Path, value: JsonValue) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--selection", choices=["manifest", "remaining", "all"], default="manifest"
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--manifest", type=Path, default=BATCH_PATH)
    args = parser.parse_args()
    if args.offset < 0 or (args.limit is not None and args.limit <= 0):
        parser.error("Offset must be nonnegative and limit must be positive")

    records = load_dataset(args.dataset)
    manifest = load_review_batch(args.manifest, args.dataset)
    selected = select_records(
        records,
        [item.review_id for item in manifest.cases],
        args.selection,
    )
    selected = selected[args.offset :]
    if args.limit is not None:
        selected = selected[: args.limit]

    provider = CompatibleChatClient.from_environment()
    if provider.provider != "ollama-local" or provider.model != EXPECTED_MODEL:
        raise ProviderError(
            f"Diagnostics require local Ollama model {EXPECTED_MODEL}; got "
            f"{provider.provider}/{provider.model}"
        )
    taxonomy = load_taxonomy()

    if args.output.exists() and not args.resume:
        raise ValueError("Output exists; use --resume to retain earlier attempts")
    args.output.mkdir(parents=True, exist_ok=True)
    metadata_path = args.output / "run.json"
    metadata = {
        "run_id": args.run_id,
        "provider": provider.provider,
        "model": provider.model,
        "dataset_path": _provenance_path(args.dataset),
        "manifest_path": _provenance_path(args.manifest),
        "human_review_status": "pending",
        "provisional_reference_is_gold": False,
        "accuracy_reported": False,
    }
    if metadata_path.exists():
        if json.loads(metadata_path.read_text("utf-8")) != metadata:
            raise ValueError("Run metadata does not match the existing output")
    else:
        _write_json(metadata_path, metadata)

    results_path = args.output / "results.json"
    rows: list[dict[str, JsonValue]] = (
        json.loads(results_path.read_text("utf-8")) if results_path.exists() else []
    )
    attempted = {str(row["review_id"]) for row in rows}
    failures = 0
    for record in selected:
        if record.review_id in attempted:
            continue
        started = perf_counter()
        client = DiagnosticClient(provider)
        result: UnderstandingResult | None = None
        error: str | None = None
        failure_stage: str | None = None
        try:
            result = analyze_documents(
                [SourceDocument(id=record.source.document_id, text=record.source.text)],
                client,
                taxonomy_version=taxonomy.understanding_version,
                competency_catalog={
                    node.id: node.description for node in taxonomy.competencies
                },
            )
        except (ProviderError, ValueError) as exc:
            error = str(exc)
            failure_stage = classify_failure(error, client.calls)
            failures += 1

        comparison: list[DiagnosticDifference] = []
        prompt_version = "+".join(
            version
            for call in client.calls
            if (version := call.prompt_version) is not None
        ) or None
        if result is not None:
            comparison = compare_snapshots(
                provisional_snapshot(record.provisional_reference.label),
                model_snapshot(result),
            )
            prompt_version = result.audit.prompt_version
        case_payload: dict[str, JsonValue] = {
            "run_id": args.run_id,
            "review_id": record.review_id,
            "review_domain": record.review_domain,
            "lineage_group": record.leakage_control.lineage_group,
            "source_sha256": record.source.text_sha256,
            "provider": provider.provider,
            "model": provider.model,
            "prompt_version": prompt_version,
            "status": "completed" if result is not None else "structural_failure",
            "failure_stage": failure_stage,
            "error": error,
            "seconds": round(perf_counter() - started, 2),
            "raw_calls": [call.model_dump(mode="json") for call in client.calls],
            "model_output": (
                result.model_dump(mode="json") if result is not None else None
            ),
            "differences_are_investigation_questions": True,
            "differences": [item.model_dump(mode="json") for item in comparison],
            "human_review_status": record.human_review.status,
            "human_final_label": None,
            "dataset_split": record.leakage_control.split,
        }
        _write_json(args.output / f"{record.review_id}.json", case_payload)
        row: dict[str, JsonValue] = {
            "review_id": record.review_id,
            "review_domain": record.review_domain,
            "lineage_group": record.leakage_control.lineage_group,
            "source_sha256": record.source.text_sha256,
            "status": case_payload["status"],
            "failure_stage": failure_stage,
            "error": error,
            "seconds": case_payload["seconds"],
            "difference_fields": [item.field for item in comparison],
            "case_artifact": f"{record.review_id}.json",
        }
        rows.append(row)
        _write_json(results_path, rows)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    summary = {
        "run_id": args.run_id,
        "attempted": len(rows),
        "completed": sum(row["status"] == "completed" for row in rows),
        "structural_failures": sum(
            row["status"] == "structural_failure" for row in rows
        ),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(args.output / "summary.json", summary)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
