"""Program-data validation and audited multi-program assessment.

Recommendation output is withheld until both the operating policy and each
program record have current, human-validated provenance.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import Field, JsonValue, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from unihive.audit import create_audited_assessment
from unihive.models import Assessment, CoreModel, ProgramConfig, StudentProfile
from unihive.resources import DATA_ROOT
from unihive.scoring import LoadedScoringConfiguration
from unihive.taxonomy import Taxonomy

DEFAULT_POLICY_PATH = DATA_ROOT / "program_data_policy.yaml"
DEFAULT_POLICY_SCHEMA = DATA_ROOT / "schemas" / "program_data_policy.schema.json"
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class ProgramDataError(ValueError):
    """Raised when program-data screening cannot run safely."""


class ProvisionalProgramDataPolicyWarning(UserWarning):
    """Warns that the program-data policy still needs human validation."""


class ProgramDataIssueCode(StrEnum):
    """A deterministic reason a record cannot support recommendations."""

    POLICY_PROVISIONAL = "POLICY_PROVISIONAL"
    POLICY_UNVALIDATED = "POLICY_UNVALIDATED"
    PROGRAM_PROVISIONAL = "PROGRAM_PROVISIONAL"
    PROGRAM_UNVALIDATED = "PROGRAM_UNVALIDATED"
    VERIFIED_IN_FUTURE = "VERIFIED_IN_FUTURE"
    SOURCE_STALE = "SOURCE_STALE"


class ProgramDataPolicy(CoreModel):
    """Human-reviewed freshness and provenance requirements."""

    version: str
    maximum_age_days: int = Field(gt=0)
    provisional: bool
    validated_by: str | None
    source: str | None


class LoadedProgramDataPolicy(CoreModel):
    """Validated policy paired with its content-derived version."""

    version: str
    values: ProgramDataPolicy


class ProgramDataReview(CoreModel):
    """Trace explaining whether one program may support recommendations."""

    program_id: str
    recommendation_ready: bool
    issues: list[ProgramDataIssueCode]
    source_url: str
    verified_on: date
    policy_version: str


class ProgramAssessmentResult(CoreModel):
    """A gated program record and its optional deterministic assessment."""

    review: ProgramDataReview
    assessment: Assessment | None
    diagnostic_only: bool


class ProgramAssessmentRun(CoreModel):
    """Auditable output for one deterministic multi-program screening run."""

    as_of: date
    policy_version: str
    taxonomy_version: str
    scoring_version: str
    engine_version: str
    results: list[ProgramAssessmentResult]


def load_program_data_policy(
    policy_path: Path = DEFAULT_POLICY_PATH,
    schema_path: Path = DEFAULT_POLICY_SCHEMA,
) -> LoadedProgramDataPolicy:
    """Load and schema-validate the versioned program-data policy."""
    try:
        document = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        )
        schema = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        )
        if not isinstance(document, dict) or not isinstance(schema, dict):
            raise ProgramDataError("policy and schema documents must be objects")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
        values = ProgramDataPolicy.model_validate(document)
    except (
        OSError,
        PydanticValidationError,
        SchemaError,
        ValidationError,
        yaml.YAMLError,
    ) as error:
        raise ProgramDataError(
            f"Invalid program-data policy {policy_path.name}: {error}"
        ) from error

    if values.provisional:
        warnings.warn(
            f"Provisional program-data policy: {values.version}",
            ProvisionalProgramDataPolicyWarning,
            stacklevel=2,
        )
    return LoadedProgramDataPolicy(
        version=f"{values.version}:{sha256(policy_path.read_bytes()).hexdigest()}",
        values=values,
    )


def review_program_data(
    program: ProgramConfig,
    *,
    as_of: date,
    policy: LoadedProgramDataPolicy,
) -> ProgramDataReview:
    """Apply provenance and freshness gates without network access."""
    issues: list[ProgramDataIssueCode] = []
    if policy.values.provisional:
        issues.append(ProgramDataIssueCode.POLICY_PROVISIONAL)
    if not policy.values.validated_by:
        issues.append(ProgramDataIssueCode.POLICY_UNVALIDATED)
    if program.provisional:
        issues.append(ProgramDataIssueCode.PROGRAM_PROVISIONAL)
    if not program.validated_by:
        issues.append(ProgramDataIssueCode.PROGRAM_UNVALIDATED)
    if program.verified_on > as_of:
        issues.append(ProgramDataIssueCode.VERIFIED_IN_FUTURE)
    elif (as_of - program.verified_on).days > policy.values.maximum_age_days:
        issues.append(ProgramDataIssueCode.SOURCE_STALE)
    return ProgramDataReview(
        program_id=program.program_id,
        recommendation_ready=not issues,
        issues=issues,
        source_url=str(program.source_url),
        verified_on=program.verified_on,
        policy_version=policy.version,
    )


def assess_programs(
    profile: StudentProfile,
    programs: Sequence[ProgramConfig],
    *,
    taxonomy: Taxonomy,
    scoring_configuration: LoadedScoringConfiguration,
    policy: LoadedProgramDataPolicy,
    as_of: date,
    timestamp: datetime,
    engine_version: str,
    include_blocked_diagnostics: bool = False,
) -> ProgramAssessmentRun:
    """Screen records, then run the deterministic engine only when allowed."""
    program_ids = [program.program_id for program in programs]
    duplicates = sorted(
        {program_id for program_id in program_ids if program_ids.count(program_id) > 1}
    )
    if duplicates:
        raise ProgramDataError("Duplicate program ids: " + ", ".join(duplicates))

    results: list[ProgramAssessmentResult] = []
    for program in sorted(programs, key=lambda item: item.program_id):
        review = review_program_data(program, as_of=as_of, policy=policy)
        should_assess = review.recommendation_ready or include_blocked_diagnostics
        assessment = (
            create_audited_assessment(
                profile,
                program,
                taxonomy=taxonomy,
                scoring_configuration=scoring_configuration,
                as_of=as_of,
                timestamp=timestamp,
                engine_version=engine_version,
            )
            if should_assess
            else None
        )
        results.append(
            ProgramAssessmentResult(
                review=review,
                assessment=assessment,
                diagnostic_only=bool(assessment) and not review.recommendation_ready,
            )
        )
    return ProgramAssessmentRun(
        as_of=as_of,
        policy_version=policy.version,
        taxonomy_version=taxonomy.version,
        scoring_version=scoring_configuration.version,
        engine_version=engine_version,
        results=results,
    )
