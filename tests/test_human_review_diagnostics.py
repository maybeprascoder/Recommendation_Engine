"""The live diagnostic runner treats provisional differences as questions."""

import json
from pathlib import Path

from qa.human_review_batch import BATCH_PATH, load_review_batch
from qa.human_review_dataset import DATASET_PATH, load_dataset
from qa.run_human_review_diagnostics import (
    SemanticSnapshot,
    _prompt_version,
    _provenance_path,
    classify_failure,
    compare_snapshots,
    select_records,
)

DIAGNOSTIC_PATH = (
    Path(__file__).parents[1] / "qa/human-review-qwen35-9b-stage4d-20260928"
)


def empty_snapshot(**updates):
    values = {
        "claims": [],
        "contexts": [],
        "demonstrated_methods": [],
        "competency_suggestions": [],
        "judgments": {},
        "unknowns": [],
        "explicit_absence": [],
        "questions": [],
        "unassessed": [],
    }
    values.update(updates)
    return SemanticSnapshot.model_validate(values)


def test_selection_starts_with_manifest_then_covers_remaining_cases():
    records = load_dataset()
    manifest = load_review_batch(BATCH_PATH)
    manifest_ids = [item.review_id for item in manifest.cases]
    selected = select_records(records, manifest_ids, "manifest")
    remaining = select_records(records, manifest_ids, "remaining")
    all_records = select_records(records, manifest_ids, "all")
    assert [record.review_id for record in selected] == manifest_ids
    assert len(selected) == 30
    assert len(remaining) == 70
    assert len(all_records) == 100
    assert {record.review_id for record in selected}.isdisjoint(
        record.review_id for record in remaining
    )


def test_comparison_reports_questions_without_correctness_labels():
    reference = empty_snapshot(judgments={"impact": ["unknown"]})
    prediction = empty_snapshot(judgments={"impact": ["reported"]})
    differences = compare_snapshots(reference, prediction)
    assert [item.field for item in differences] == ["judgments"]
    assert "source support" in differences[0].question
    assert "correct" not in differences[0].model_dump_json().lower()


def test_identical_snapshots_have_no_investigation_questions():
    snapshot = empty_snapshot(explicit_absence=["No networking experience."])
    assert compare_snapshots(snapshot, snapshot) == []


def test_failure_classification_distinguishes_pipeline_stages():
    assert (
        classify_failure("Support review failed validation or target coverage", [])
        == "support_review_validation"
    )
    assert (
        classify_failure("Interpretation failed schema or provenance validation", [])
        == "understanding_parse_or_validation"
    )


def test_prompt_version_is_retained_before_pipeline_validation():
    assert _prompt_version("version: understanding-v9\nReturn JSON.") == (
        "understanding-v9"
    )
    assert _prompt_version("Return JSON.") is None


def test_repository_provenance_paths_are_portable():
    assert _provenance_path(DATASET_PATH) == "qa/human_review_cases.jsonl"


def test_checked_in_diagnostics_have_complete_non_gold_provenance():
    records = {record.review_id: record for record in load_dataset()}
    rows = json.loads((DIAGNOSTIC_PATH / "results.json").read_text("utf-8"))
    assert len(rows) == 100
    assert len({row["review_id"] for row in rows}) == 100

    for row in rows:
        record = records[row["review_id"]]
        payload = json.loads(
            (DIAGNOSTIC_PATH / row["case_artifact"]).read_text("utf-8")
        )
        assert payload["run_id"] == "stage4d-qwen35-9b-20260928"
        assert payload["source_sha256"] == record.source.text_sha256
        assert payload["provider"] == "ollama-local"
        assert payload["model"] == "qwen3.5:9b"
        assert payload["prompt_version"]
        assert payload["human_review_status"] == "pending"
        assert payload["human_final_label"] is None
        assert payload["dataset_split"] == record.leakage_control.split
        assert payload["dataset_split"] == "unassigned"
        assert payload["differences_are_investigation_questions"] is True
        assert payload["raw_calls"]
        assert all(call["prompt_version"] for call in payload["raw_calls"])
        if payload["status"] == "completed":
            assert payload["model_output"]["scoring_enabled"] is False
        else:
            assert payload["status"] == "structural_failure"
            assert payload["model_output"] is None
            assert payload["error"]
