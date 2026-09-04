"""Recorded-fixture tests for the mocked LLM extraction boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from unihive.llm.extractor import (
    ExtractionFailedError,
    extract_student_profile,
)
from unihive.models import EvidenceState, StudentProfile

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "extractor"
RAW_INPUT = (FIXTURE_DIR / "resume.txt").read_text(encoding="utf-8")
VALID_RESPONSE = (FIXTURE_DIR / "valid_response.json").read_text(encoding="utf-8")
INVALID_RESPONSE = (FIXTURE_DIR / "invalid_response.json").read_text(
    encoding="utf-8"
)


class RecordedClient:
    """Offline mock that replays recorded model responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return next(self._responses)


def test_valid_recorded_response_builds_profile_and_confirmation_payload() -> None:
    client = RecordedClient([VALID_RESPONSE])

    result = extract_student_profile(RAW_INPUT, client)

    assert type(result.profile) is StudentProfile
    assert result.attempts_used == 1
    assert len(client.prompts) == 1
    assert result.prompt_version.startswith("extractor-v1+extractor-retry-v1:")
    assert result.confirmation_payload.profile == result.profile
    assert result.confirmation_payload.requires_confirmation is True
    source_spans = [
        item.source_span for item in result.confirmation_payload.evidence_items
    ]
    assert source_spans == [
        "CS 301: Operating Systems",
        "Python scheduler project",
    ]
    assert all(
        item.state is EvidenceState.VERIFIED_PRESENT
        for item in result.confirmation_payload.evidence_items
    )


def test_validation_failure_retries_once_with_error_then_succeeds() -> None:
    client = RecordedClient([INVALID_RESPONSE, VALID_RESPONSE])

    result = extract_student_profile(RAW_INPUT, client)

    assert result.attempts_used == 2
    assert len(client.prompts) == 2
    assert "extraction_confidence" in client.prompts[1]
    assert INVALID_RESPONSE in client.prompts[1]


def test_two_invalid_responses_fail_loudly_without_a_third_call() -> None:
    client = RecordedClient([INVALID_RESPONSE, INVALID_RESPONSE])

    with pytest.raises(ExtractionFailedError, match="after one retry"):
        extract_student_profile(RAW_INPUT, client)

    assert len(client.prompts) == 2


def test_non_verbatim_source_span_is_rejected_and_retried() -> None:
    response_document = json.loads(VALID_RESPONSE)
    response_document["evidence"][0]["source"] = "Invented course source"
    invalid_source = json.dumps(response_document)
    client = RecordedClient([invalid_source, VALID_RESPONSE])

    result = extract_student_profile(RAW_INPUT, client)

    assert result.attempts_used == 2
    assert "verbatim input span" in client.prompts[1]


def test_prompt_forbids_inference_and_requires_unknown_state() -> None:
    client = RecordedClient([VALID_RESPONSE])

    extract_student_profile(RAW_INPUT, client)

    prompt = client.prompts[0]
    assert "Anything not clearly stated is UNKNOWN" in prompt
    assert "Never infer a skill or competency from an adjacent skill" in prompt


def test_markdown_wrapped_json_is_not_coerced_or_patched() -> None:
    wrapped = f"```json\n{VALID_RESPONSE}\n```"
    client = RecordedClient([wrapped, wrapped])

    with pytest.raises(ExtractionFailedError):
        extract_student_profile(RAW_INPUT, client)

    assert len(client.prompts) == 2
