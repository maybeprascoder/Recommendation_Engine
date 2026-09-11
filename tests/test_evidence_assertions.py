"""The evaluation runner must distinguish valid JSON from expected behavior."""

from __future__ import annotations

from test_understanding import TEXT, example, parse, review_for

from qa.evidence_assertions import check_behavior
from unihive.llm.analysis_cli import RecordedClient, RecordedResponses
from unihive.llm.understanding import analyze_documents
from unihive.understanding import (
    SourceDocument,
    SupportReview,
    complete_unknown_dimensions,
    load_evaluation_rubric,
)


def result_for(data):
    draft = complete_unknown_dimensions(parse(data), load_evaluation_rubric())
    return analyze_documents(
        [SourceDocument(id="document-1", text=TEXT)],
        RecordedClient(
            RecordedResponses(
                draft=draft,
                review=SupportReview(**review_for(draft.model_dump(mode="json"))),
            )
        ),
        taxonomy_version="test",
        competency_catalog={},
    )


def test_schema_valid_but_behaviorally_wrong_output_fails():
    result = result_for(example())
    assert check_behavior("keyword-list", result)


def test_missing_behavior_oracle_is_not_reported_as_pass():
    assert check_behavior("unconfigured-case", result_for(example())) is None


def test_empty_profile_passes_skill_list_behavior_checks():
    data = {key: [] for key in example()}
    assert check_behavior("keyword-list", result_for(data)) == []


def test_duplicate_behavior_check_detects_missed_group():
    data = example()
    data["claims"].append(dict(data["claims"][0], id="c2"))
    assert check_behavior("duplicate-work", result_for(data))
