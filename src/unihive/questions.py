"""Deterministic next-best-question ranking.

Implements Build Spec section 7 and Experience Doc section 2, Phase 2.
"""

from __future__ import annotations

import warnings
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Self

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import JsonValue, TypeAdapter, model_validator
from pydantic import ValidationError as PydanticValidationError

from unihive.models import (
    Assessment,
    CompetencyScoreTrace,
    CoreModel,
    ScoreExclusionReason,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS_PATH = PROJECT_ROOT / "data" / "questions.yaml"
DEFAULT_QUESTIONS_SCHEMA = (
    PROJECT_ROOT / "data" / "schemas" / "questions.schema.json"
)
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class QuestionRankingError(ValueError):
    """Raised when question ranking cannot be reproduced safely."""


class QuestionBankConfigurationError(QuestionRankingError):
    """Raised when the versioned question bank is invalid."""


class ProvisionalQuestionBankWarning(UserWarning):
    """Warns that an unvalidated question bank is in use."""


class QuestionResolutionType(StrEnum):
    """The kind of unknown that a question is designed to resolve."""

    COMPETENCY = "COMPETENCY"
    FIELD = "FIELD"


class QuestionBankEntry(CoreModel):
    """One deterministic question and the uncertainty it resolves."""

    id: str
    text: str
    resolves_type: QuestionResolutionType
    resolves_id: str


class QuestionBank(CoreModel):
    """Versioned progressive-questioning content."""

    version: str
    provisional: bool
    validated_by: str | None
    source: str | None
    questions: tuple[QuestionBankEntry, ...]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        ids = [question.id for question in self.questions]
        duplicates = sorted(
            {question_id for question_id in ids if ids.count(question_id) > 1}
        )
        if duplicates:
            raise ValueError("duplicate question ids: " + ", ".join(duplicates))
        return self


class LoadedQuestionBank(CoreModel):
    """Validated question content paired with a content-derived version."""

    version: str
    values: QuestionBank


class RankedQuestion(CoreModel):
    """A relevant question with its deterministic expected-effect trace."""

    question_id: str
    text: str
    resolves_type: QuestionResolutionType
    resolves_id: str
    demand_weight: Decimal | None
    expected_effect: str
    question_bank_version: str


def load_question_bank(
    questions_path: Path = DEFAULT_QUESTIONS_PATH,
    schema_path: Path = DEFAULT_QUESTIONS_SCHEMA,
) -> LoadedQuestionBank:
    """Load and schema-validate the versioned progressive question bank."""
    try:
        document = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(questions_path.read_text(encoding="utf-8"))
        )
        schema = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        )
        if not isinstance(document, dict) or not isinstance(schema, dict):
            raise QuestionBankConfigurationError(
                "question-bank and schema documents must be objects"
            )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
        values = QuestionBank.model_validate(document)
    except (
        OSError,
        PydanticValidationError,
        SchemaError,
        ValidationError,
        yaml.YAMLError,
    ) as error:
        raise QuestionBankConfigurationError(
            f"Invalid question bank {questions_path.name}: {error}"
        ) from error

    if values.provisional:
        warnings.warn(
            f"Provisional question bank: {values.version}",
            ProvisionalQuestionBankWarning,
            stacklevel=2,
        )
    content_hash = sha256(questions_path.read_bytes()).hexdigest()
    return LoadedQuestionBank(
        version=f"{values.version}:{content_hash}", values=values
    )


def rank_questions(
    assessment: Assessment,
    *,
    question_bank: LoadedQuestionBank | None = None,
) -> list[RankedQuestion]:
    """Rank unresolved questions by target-program competency demand."""
    loaded = question_bank or load_question_bank()
    traces = _index_traces(assessment.program_alignment.competency_trace)
    missing_fields = set(assessment.audit.missing_fields)
    competency_questions: list[tuple[Decimal, int, RankedQuestion]] = []
    field_questions: list[tuple[int, RankedQuestion]] = []

    for bank_order, question in enumerate(loaded.values.questions):
        if question.resolves_type is QuestionResolutionType.COMPETENCY:
            trace = traces.get(question.resolves_id)
            if trace is None or (
                trace.exclusion_reason is not ScoreExclusionReason.UNKNOWN
            ):
                continue
            ranked = RankedQuestion(
                question_id=question.id,
                text=question.text,
                resolves_type=question.resolves_type,
                resolves_id=question.resolves_id,
                demand_weight=trace.demand_weight,
                expected_effect=_competency_effect(question, trace),
                question_bank_version=loaded.version,
            )
            competency_questions.append((trace.demand_weight, bank_order, ranked))
            continue

        if question.resolves_id not in missing_fields:
            continue
        field_questions.append(
            (
                bank_order,
                RankedQuestion(
                    question_id=question.id,
                    text=question.text,
                    resolves_type=question.resolves_type,
                    resolves_id=question.resolves_id,
                    demand_weight=None,
                    expected_effect=_field_effect(question),
                    question_bank_version=loaded.version,
                ),
            )
        )

    competency_questions.sort(key=lambda item: (-item[0], item[1]))
    field_questions.sort(key=lambda item: item[0])
    return [
        *(item[2] for item in competency_questions),
        *(item[1] for item in field_questions),
    ]


def next_best_question(
    assessment: Assessment,
    *,
    question_bank: LoadedQuestionBank | None = None,
) -> RankedQuestion | None:
    """Return the first demand-ranked question, if uncertainty remains."""
    ranked = rank_questions(assessment, question_bank=question_bank)
    return next(iter(ranked), None)


def _index_traces(
    traces: list[CompetencyScoreTrace],
) -> dict[str, CompetencyScoreTrace]:
    indexed: dict[str, CompetencyScoreTrace] = {}
    for trace in traces:
        if trace.competency_id in indexed:
            raise QuestionRankingError(
                f"Duplicate competency trace: {trace.competency_id}"
            )
        indexed[trace.competency_id] = trace
    return indexed


def _competency_effect(
    question: QuestionBankEntry,
    trace: CompetencyScoreTrace,
) -> str:
    label = question.resolves_id.replace("_", " ")
    weight = format(trace.demand_weight.normalize(), "f")
    return (
        f"This would resolve {label}, currently unknown with demand weight "
        f"{weight} for your target."
    )


def _field_effect(question: QuestionBankEntry) -> str:
    label = question.resolves_id.replace("_", " ")
    return f"This would resolve {label}, currently missing from the assessment."
