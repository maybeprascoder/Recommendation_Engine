"""LLM narration over frozen assessment and report data only."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Protocol

from unihive.llm.extractor import PromptTemplate, load_prompt_template
from unihive.models import Assessment, CoreModel
from unihive.report import ReportStructure

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_NARRATOR_PROMPT = PROMPTS_DIR / "narrator_v1.txt"
BANNED_NARRATION_TERMS = ("%", "chance", "probability", "odds", "likelihood")


class NarrationError(ValueError):
    """Raised when narration violates the frozen-data output contract."""


class NarrationClient(Protocol):
    """Minimal injected LLM boundary used by the narrator."""

    def complete(self, prompt: str) -> str:
        """Return prose for one fully rendered prompt."""
        ...


class NarrationResult(CoreModel):
    """Validated prose paired with its content-derived prompt version."""

    prose: str
    prompt_version: str


def narrate_report(
    assessment: Assessment,
    report: ReportStructure,
    client: NarrationClient,
    *,
    prompt_path: Path = DEFAULT_NARRATOR_PROMPT,
) -> NarrationResult:
    """Narrate frozen inputs without recomputing or reordering their content."""
    template = load_prompt_template(prompt_path)
    prompt = template.render(
        {
            "assessment_json": assessment.model_dump_json(),
            "report_json": report.model_dump_json(),
        }
    )
    prose = client.complete(prompt).strip()
    if not prose:
        raise NarrationError("Narrator returned empty prose")
    normalized = prose.casefold()
    violations = [
        term for term in BANNED_NARRATION_TERMS if term in normalized
    ]
    if violations:
        raise NarrationError(
            "Narrator used forbidden admission language: "
            + ", ".join(violations)
        )
    return NarrationResult(
        prose=prose,
        prompt_version=_prompt_version(template, prompt_path),
    )


def narrate(
    assessment: Assessment,
    report: ReportStructure,
    client: NarrationClient,
    *,
    prompt_path: Path = DEFAULT_NARRATOR_PROMPT,
) -> NarrationResult:
    """Concise public alias for ``narrate_report``."""
    return narrate_report(assessment, report, client, prompt_path=prompt_path)


def _prompt_version(template: PromptTemplate, path: Path) -> str:
    return f"{template.version}:{sha256(path.read_bytes()).hexdigest()}"
