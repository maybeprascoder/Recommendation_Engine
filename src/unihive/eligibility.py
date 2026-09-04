"""Deterministic, sourced program eligibility evaluation.

Implements Build Spec section 5.4 -- eligibility remains separate from
readiness and never calls an LLM or the network.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import JsonValue, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from unihive.models import (
    CitizenshipResidencyRule,
    DeadlineRule,
    EligibilityFailureEffect,
    EligibilityResult,
    EligibilityRule,
    EligibilityRuleBase,
    EligibilityRuleOutcome,
    EligibilityRuleResult,
    EligibilityStatus,
    EnglishScoreRule,
    GRERequirementRule,
    IntakeAvailabilityRule,
    MandatoryCourseworkRule,
    MinimumGPARule,
    ProgramConfig,
    RequiredPriorDegreeRule,
    StructuredRecord,
    StudentProfile,
    WorkExperienceRule,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROGRAM_SCHEMA = PROJECT_ROOT / "data" / "schemas" / "program.schema.json"
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class ProgramConfigError(ValueError):
    """Raised when a program YAML file is missing or invalid."""


class ProvisionalProgramWarning(UserWarning):
    """Warns that an unvalidated program configuration is in use."""


def load_program_config(
    program_path: Path,
    schema_path: Path = DEFAULT_PROGRAM_SCHEMA,
) -> ProgramConfig:
    """Load and schema-validate a sourced program YAML configuration."""
    try:
        document = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(program_path.read_text(encoding="utf-8"))
        )
        schema = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        )
        if not isinstance(document, dict) or not isinstance(schema, dict):
            raise ProgramConfigError("program and schema documents must be objects")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
        program = ProgramConfig.model_validate(document)
    except (
        OSError,
        PydanticValidationError,
        SchemaError,
        ValidationError,
        yaml.YAMLError,
    ) as error:
        raise ProgramConfigError(
            f"Invalid program configuration {program_path.name}: {error}"
        ) from error

    if program.provisional:
        warnings.warn(
            f"Provisional program configuration: {program.program_id}",
            ProvisionalProgramWarning,
            stacklevel=2,
        )
    return program


def evaluate_eligibility(
    profile: StudentProfile,
    program: ProgramConfig,
    *,
    as_of: date,
) -> EligibilityResult:
    """Evaluate every configured rule without inference or external calls."""
    if not program.eligibility_rules:
        return EligibilityResult(
            status=EligibilityStatus.ELIGIBILITY_UNKNOWN,
            rule_breakdown=[],
            needed_information=["program.eligibility_rules"],
        )

    breakdown = [
        _evaluate_rule(profile, rule, as_of=as_of)
        for rule in program.eligibility_rules
    ]
    needed_information = _ordered_unique(
        item
        for result in breakdown
        if result.outcome is EligibilityRuleOutcome.UNKNOWN
        for item in result.needed_information
    )

    hard_failure = any(
        result.outcome is EligibilityRuleOutcome.FAIL
        and rule.failure_effect
        is EligibilityFailureEffect.NOT_CURRENTLY_ELIGIBLE
        for rule, result in zip(
            program.eligibility_rules, breakdown, strict=True
        )
    )
    conditional_failure = any(
        result.outcome is EligibilityRuleOutcome.FAIL
        and rule.failure_effect is EligibilityFailureEffect.CONDITIONALLY_ELIGIBLE
        for rule, result in zip(
            program.eligibility_rules, breakdown, strict=True
        )
    )
    has_unknown = any(
        result.outcome is EligibilityRuleOutcome.UNKNOWN for result in breakdown
    )

    if hard_failure:
        status = EligibilityStatus.NOT_CURRENTLY_ELIGIBLE
    elif has_unknown:
        status = EligibilityStatus.ELIGIBILITY_UNKNOWN
    elif conditional_failure:
        status = EligibilityStatus.CONDITIONALLY_ELIGIBLE
    else:
        status = EligibilityStatus.ELIGIBLE

    return EligibilityResult(
        status=status,
        rule_breakdown=breakdown,
        needed_information=needed_information,
    )


def check_eligibility(
    profile: StudentProfile,
    program: ProgramConfig,
    *,
    as_of: date,
) -> EligibilityResult:
    """Compatibility name for deterministic eligibility evaluation."""
    return evaluate_eligibility(profile, program, as_of=as_of)


def _evaluate_rule(
    profile: StudentProfile,
    rule: EligibilityRule,
    *,
    as_of: date,
) -> EligibilityRuleResult:
    if isinstance(rule, RequiredPriorDegreeRule):
        return _required_prior_degree(profile, rule)
    if isinstance(rule, MinimumGPARule):
        return _minimum_gpa(profile, rule)
    if isinstance(rule, MandatoryCourseworkRule):
        return _mandatory_coursework(profile, rule)
    if isinstance(rule, EnglishScoreRule):
        return _english_score(profile, rule)
    if isinstance(rule, GRERequirementRule):
        return _gre_requirement(profile, rule)
    if isinstance(rule, WorkExperienceRule):
        return _work_experience(profile, rule)
    if isinstance(rule, CitizenshipResidencyRule):
        return _citizenship_residency(profile, rule)
    if isinstance(rule, DeadlineRule):
        outcome = (
            EligibilityRuleOutcome.PASS
            if as_of <= rule.deadline
            else EligibilityRuleOutcome.FAIL
        )
        return _result(rule, outcome)
    if isinstance(rule, IntakeAvailabilityRule):
        if rule.available is None:
            return _result(rule, EligibilityRuleOutcome.UNKNOWN, "program.intake")
        outcome = (
            EligibilityRuleOutcome.PASS
            if rule.available
            else EligibilityRuleOutcome.FAIL
        )
        return _result(rule, outcome)
    raise TypeError(f"Unsupported eligibility rule: {type(rule).__name__}")


def _required_prior_degree(
    profile: StudentProfile, rule: RequiredPriorDegreeRule
) -> EligibilityRuleResult:
    accepted = {_normalize(value) for value in rule.accepted_degrees}
    complete_records: list[tuple[str, bool]] = []
    for record in profile.academic_history:
        degree = _text(record, "degree")
        completed = record.get("completed")
        if degree is not None and isinstance(completed, bool):
            complete_records.append((_normalize(degree), completed))

    if any(degree in accepted and completed for degree, completed in complete_records):
        return _result(rule, EligibilityRuleOutcome.PASS)
    if complete_records:
        return _result(rule, EligibilityRuleOutcome.FAIL)
    return _result(
        rule,
        EligibilityRuleOutcome.UNKNOWN,
        "academic_history.degree",
        "academic_history.completed",
    )


def _minimum_gpa(
    profile: StudentProfile, rule: MinimumGPARule
) -> EligibilityRuleResult:
    if profile.normalized_gpa is None:
        return _result(rule, EligibilityRuleOutcome.UNKNOWN, "normalized_gpa")
    outcome = (
        EligibilityRuleOutcome.PASS
        if profile.normalized_gpa >= rule.minimum_gpa
        else EligibilityRuleOutcome.FAIL
    )
    return _result(rule, outcome)


def _mandatory_coursework(
    profile: StudentProfile, rule: MandatoryCourseworkRule
) -> EligibilityRuleResult:
    statuses: dict[str, bool] = {}
    for record in profile.courses:
        course = _text(record, "course_id") or _text(record, "name")
        completed = record.get("completed")
        if course is not None and isinstance(completed, bool):
            statuses[_normalize(course)] = completed

    required = [_normalize(course) for course in rule.required_courses]
    if any(course in statuses and not statuses[course] for course in required):
        return _result(rule, EligibilityRuleOutcome.FAIL)

    missing = [course for course in required if course not in statuses]
    if missing:
        return _result(
            rule,
            EligibilityRuleOutcome.UNKNOWN,
            *(f"courses.{course}" for course in missing),
        )
    return _result(rule, EligibilityRuleOutcome.PASS)


def _english_score(
    profile: StudentProfile, rule: EnglishScoreRule
) -> EligibilityRuleResult:
    thresholds = {
        _normalize(test_name): threshold
        for test_name, threshold in rule.minimum_scores.items()
    }
    scored: list[tuple[Decimal, Decimal]] = []
    recognized_without_score = False
    for record in profile.tests:
        test_name = _text(record, "test") or _text(record, "name")
        if test_name is None or _normalize(test_name) not in thresholds:
            continue
        threshold = thresholds[_normalize(test_name)]
        score = _decimal(record.get("score"))
        if score is None:
            recognized_without_score = True
        else:
            scored.append((score, threshold))

    if any(score >= threshold for score, threshold in scored):
        return _result(rule, EligibilityRuleOutcome.PASS)
    if recognized_without_score or not scored:
        accepted_names = ",".join(sorted(thresholds))
        return _result(
            rule,
            EligibilityRuleOutcome.UNKNOWN,
            f"tests.{accepted_names}.score",
        )
    return _result(rule, EligibilityRuleOutcome.FAIL)


def _gre_requirement(
    profile: StudentProfile, rule: GRERequirementRule
) -> EligibilityRuleResult:
    if not rule.required:
        return _result(rule, EligibilityRuleOutcome.NOT_APPLICABLE)

    gre_records = [
        record
        for record in profile.tests
        if _normalize(_text(record, "test") or _text(record, "name") or "")
        == "gre"
    ]
    if not gre_records:
        return _result(rule, EligibilityRuleOutcome.UNKNOWN, "tests.gre")

    scores = [
        score
        for record in gre_records
        if (score := _decimal(record.get("score"))) is not None
    ]
    if rule.minimum_score is not None:
        if any(score >= rule.minimum_score for score in scores):
            return _result(rule, EligibilityRuleOutcome.PASS)
        if scores:
            return _result(rule, EligibilityRuleOutcome.FAIL)
        return _result(rule, EligibilityRuleOutcome.UNKNOWN, "tests.gre.score")

    taken_values = [record.get("taken") for record in gre_records]
    if scores or any(value is True for value in taken_values):
        return _result(rule, EligibilityRuleOutcome.PASS)
    if taken_values and all(value is False for value in taken_values):
        return _result(rule, EligibilityRuleOutcome.FAIL)
    return _result(rule, EligibilityRuleOutcome.UNKNOWN, "tests.gre.taken")


def _work_experience(
    profile: StudentProfile, rule: WorkExperienceRule
) -> EligibilityRuleResult:
    if not profile.work:
        return _result(rule, EligibilityRuleOutcome.UNKNOWN, "work.months")

    reported_totals = [
        months
        for record in profile.work
        if (months := _nonnegative_integer(record.get("total_months"))) is not None
    ]
    if reported_totals:
        total_months = max(reported_totals)
        outcome = (
            EligibilityRuleOutcome.PASS
            if total_months >= rule.minimum_months
            else EligibilityRuleOutcome.FAIL
        )
        return _result(rule, outcome)

    durations = [
        months
        for record in profile.work
        if (months := _nonnegative_integer(record.get("months"))) is not None
    ]
    known_months = sum(durations)
    if known_months >= rule.minimum_months:
        return _result(rule, EligibilityRuleOutcome.PASS)
    if len(durations) == len(profile.work):
        return _result(rule, EligibilityRuleOutcome.FAIL)
    return _result(rule, EligibilityRuleOutcome.UNKNOWN, "work.months")


def _citizenship_residency(
    profile: StudentProfile, rule: CitizenshipResidencyRule
) -> EligibilityRuleResult:
    accepted_citizenships = {
        _normalize(value) for value in rule.accepted_citizenships
    }
    accepted_residencies = {_normalize(value) for value in rule.accepted_residencies}
    if not accepted_citizenships and not accepted_residencies:
        return _result(rule, EligibilityRuleOutcome.NOT_APPLICABLE)

    if (
        profile.citizenship is not None
        and _normalize(profile.citizenship) in accepted_citizenships
    ) or (
        profile.residency is not None
        and _normalize(profile.residency) in accepted_residencies
    ):
        return _result(rule, EligibilityRuleOutcome.PASS)

    missing: list[str] = []
    if accepted_citizenships and profile.citizenship is None:
        missing.append("citizenship")
    if accepted_residencies and profile.residency is None:
        missing.append("residency")
    if missing:
        return _result(rule, EligibilityRuleOutcome.UNKNOWN, *missing)
    return _result(rule, EligibilityRuleOutcome.FAIL)


def _result(
    rule: EligibilityRuleBase,
    outcome: EligibilityRuleOutcome,
    *needed_information: str,
) -> EligibilityRuleResult:
    return EligibilityRuleResult(
        rule_id=rule.id,
        rule_type=rule.type,
        outcome=outcome,
        source_url=rule.source_url,
        needed_information=list(needed_information),
    )


def _text(record: StructuredRecord, key: str) -> str | None:
    value = record.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _decimal(value: JsonValue | None) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _nonnegative_integer(value: JsonValue | None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _ordered_unique(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique
