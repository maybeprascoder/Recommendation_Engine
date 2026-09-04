"""LLM-backed, schema-validated student-profile extraction boundary."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol

from pydantic import ValidationError

from unihive.models import (
    Confidence,
    CoreModel,
    EvidenceState,
    StudentProfile,
)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_EXTRACTION_PROMPT = PROMPTS_DIR / "extractor_v1.txt"
DEFAULT_RETRY_PROMPT = PROMPTS_DIR / "extractor_retry_v1.txt"
VERSION_PREFIX = "version:"


class ExtractorError(ValueError):
    """Base error for prompt loading and extraction validation."""


class PromptTemplateError(ExtractorError):
    """Raised when a versioned prompt template cannot be rendered."""


class ExtractionValidationError(ExtractorError):
    """Raised when one model response is not a valid sourced profile."""


class ExtractionFailedError(ExtractorError):
    """Raised after both the initial response and single retry are invalid."""


class ExtractionClient(Protocol):
    """Minimal injected LLM boundary used by the extractor."""

    def complete(self, prompt: str) -> str:
        """Return a JSON response for one fully rendered prompt."""
        ...


class PromptTemplate(CoreModel):
    """A file-backed prompt template with an explicit version."""

    version: str
    text: str

    def render(self, replacements: Mapping[str, str]) -> str:
        """Render declared placeholders without interpreting JSON braces."""
        placeholders = set(re.findall(r"\{\{([a-z_]+)\}\}", self.text))
        replacement_names = set(replacements)
        if placeholders != replacement_names:
            missing = sorted(placeholders - replacement_names)
            unexpected = sorted(replacement_names - placeholders)
            raise PromptTemplateError(
                f"Prompt replacement mismatch; missing={missing}, "
                f"unexpected={unexpected}"
            )

        rendered = self.text
        for name, value in replacements.items():
            token = "{{" + name + "}}"
            rendered = rendered.replace(token, value)
        return rendered


class ConfirmationEvidence(CoreModel):
    """One extracted claim rendered with provenance for student review."""

    evidence_id: str
    extracted_text: str
    state: EvidenceState
    source_span: str
    extraction_confidence: Confidence


class ConfirmationPayload(CoreModel):
    """The complete extraction presented before deterministic scoring."""

    profile: StudentProfile
    evidence_items: list[ConfirmationEvidence]
    requires_confirmation: Literal[True] = True


class ExtractionResult(CoreModel):
    """A validated profile and its mandatory confirmation representation."""

    profile: StudentProfile
    confirmation_payload: ConfirmationPayload
    prompt_version: str
    attempts_used: int


def extract_student_profile(
    raw_input: str,
    client: ExtractionClient,
    *,
    extraction_prompt_path: Path = DEFAULT_EXTRACTION_PROMPT,
    retry_prompt_path: Path = DEFAULT_RETRY_PROMPT,
) -> ExtractionResult:
    """Extract a profile, retrying exactly once after validation failure."""
    extraction_template = load_prompt_template(extraction_prompt_path)
    retry_template = load_prompt_template(retry_prompt_path)
    schema = json.dumps(StudentProfile.model_json_schema(), sort_keys=True)
    first_prompt = extraction_template.render(
        {"profile_schema": schema, "student_input": raw_input}
    )
    first_response = client.complete(first_prompt)

    try:
        profile = _validate_response(first_response, raw_input)
    except ExtractionValidationError as first_error:
        retry_prompt = retry_template.render(
            {
                "profile_schema": schema,
                "student_input": raw_input,
                "previous_response": first_response,
                "validation_error": str(first_error),
            }
        )
        retry_response = client.complete(retry_prompt)
        try:
            profile = _validate_response(retry_response, raw_input)
        except ExtractionValidationError as retry_error:
            raise ExtractionFailedError(
                "LLM extraction remained invalid after one retry: "
                f"{retry_error}"
            ) from retry_error
        attempts_used = 2
    else:
        attempts_used = 1

    confirmation_payload = render_confirmation_payload(profile)
    return ExtractionResult(
        profile=profile,
        confirmation_payload=confirmation_payload,
        prompt_version=_combined_prompt_version(
            extraction_template,
            retry_template,
            extraction_prompt_path,
            retry_prompt_path,
        ),
        attempts_used=attempts_used,
    )


def extract_profile(
    raw_input: str,
    client: ExtractionClient,
    *,
    extraction_prompt_path: Path = DEFAULT_EXTRACTION_PROMPT,
    retry_prompt_path: Path = DEFAULT_RETRY_PROMPT,
) -> ExtractionResult:
    """Concise public alias for ``extract_student_profile``."""
    return extract_student_profile(
        raw_input,
        client,
        extraction_prompt_path=extraction_prompt_path,
        retry_prompt_path=retry_prompt_path,
    )


def load_prompt_template(path: Path) -> PromptTemplate:
    """Load a prompt whose first line declares ``version: <value>``."""
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PromptTemplateError(f"Unable to read prompt template {path}") from error

    first_line, separator, body = payload.partition("\n")
    key, delimiter, version = first_line.partition(":")
    if (
        not separator
        or not delimiter
        or key.strip().casefold() != VERSION_PREFIX.removesuffix(":")
        or not version.strip()
        or not body.strip()
    ):
        raise PromptTemplateError(
            f"Prompt template {path.name} must start with a version line"
        )
    return PromptTemplate(version=version.strip(), text=body)


def render_confirmation_payload(profile: StudentProfile) -> ConfirmationPayload:
    """Render every sourced evidence item for confirmation or correction."""
    evidence_items: list[ConfirmationEvidence] = []
    for evidence in profile.evidence:
        if evidence.source is None or not evidence.source.strip():
            raise ExtractionValidationError(
                f"Evidence {evidence.id} has no source span"
            )
        evidence_items.append(
            ConfirmationEvidence(
                evidence_id=evidence.id,
                extracted_text=evidence.raw_text,
                state=evidence.state,
                source_span=evidence.source,
                extraction_confidence=evidence.extraction_confidence,
            )
        )
    return ConfirmationPayload(profile=profile, evidence_items=evidence_items)


def _validate_response(response: str, raw_input: str) -> StudentProfile:
    try:
        profile = StudentProfile.model_validate_json(response, strict=True)
    except (ValidationError, ValueError) as error:
        raise ExtractionValidationError(str(error)) from error

    source_errors = [
        evidence.id
        for evidence in profile.evidence
        if evidence.source is None
        or not evidence.source.strip()
        or evidence.source not in raw_input
    ]
    if source_errors:
        raise ExtractionValidationError(
            "Evidence source must be a non-empty verbatim input span: "
            + ", ".join(source_errors)
        )
    return profile


def _combined_prompt_version(
    extraction_template: PromptTemplate,
    retry_template: PromptTemplate,
    extraction_path: Path,
    retry_path: Path,
) -> str:
    digest = sha256()
    for path in (extraction_path, retry_path):
        payload = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return (
        f"{extraction_template.version}+{retry_template.version}:"
        f"{digest.hexdigest()}"
    )
