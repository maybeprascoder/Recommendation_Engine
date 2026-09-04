"""Balanced program portfolio construction.

Implements Build Spec section 5.6. Balance is an explicit objective applied
after hard student constraints, rather than a top-N score selection.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Self, TypeVar

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import Field, JsonValue, TypeAdapter, model_validator
from pydantic import ValidationError as PydanticValidationError

from unihive.models import Confidence, CoreModel, ReadinessBand

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PORTFOLIO_PATH = PROJECT_ROOT / "data" / "portfolio.yaml"
DEFAULT_PORTFOLIO_SCHEMA = (
    PROJECT_ROOT / "data" / "schemas" / "portfolio.schema.json"
)
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
T = TypeVar("T")


class PortfolioError(ValueError):
    """Raised when a balanced portfolio cannot be evaluated safely."""


class PortfolioConfigurationError(PortfolioError):
    """Raised when the versioned portfolio configuration is invalid."""


class ProvisionalPortfolioWarning(UserWarning):
    """Warns that unvalidated portfolio configuration is in use."""


class PortfolioCategory(StrEnum):
    """Categorical program position in a balanced application portfolio."""

    SAFE = "SAFE"
    TARGET = "TARGET"
    AMBITIOUS = "AMBITIOUS"


class CareerAlignment(StrEnum):
    """Categorical alignment with the student's stated career direction."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PortfolioIssueCode(StrEnum):
    """Reasons the feasible candidates cannot produce the configured balance."""

    CATEGORY_MINIMUM_NOT_MET = "CATEGORY_MINIMUM_NOT_MET"
    MINIMUM_PORTFOLIO_SIZE_NOT_MET = "MINIMUM_PORTFOLIO_SIZE_NOT_MET"


class ScoredProgramCandidate(CoreModel):
    """Categorical scored-program facts used for portfolio construction."""

    program_id: str
    program_name: str
    category: PortfolioCategory
    readiness_band: ReadinessBand
    annual_cost: Decimal | None = Field(ge=0)
    funding_available: bool | None
    location: str | None
    career_alignment: CareerAlignment
    data_confidence: Confidence


class StudentPortfolioConstraints(CoreModel):
    """Hard student constraints applied before balancing the portfolio."""

    maximum_annual_cost: Decimal | None = Field(default=None, ge=0)
    funding_required: bool = False
    allowed_locations: tuple[str, ...] = ()
    minimum_career_alignment: CareerAlignment | None = None
    minimum_data_confidence: Confidence | None = None


class PortfolioCategoryTarget(CoreModel):
    """Configured minimum and preferred count for one portfolio category."""

    minimum_count: int = Field(gt=0)
    target_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.minimum_count > self.target_count:
            raise ValueError("minimum_count must not exceed target_count")
        return self


class PortfolioConfiguration(CoreModel):
    """Versioned list-size and category-distribution configuration."""

    version: str
    provisional: bool
    validated_by: str | None
    source: str | None
    minimum_size: int = Field(gt=0)
    maximum_size: int = Field(gt=0)
    target_distribution: dict[PortfolioCategory, PortfolioCategoryTarget]

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        if self.minimum_size > self.maximum_size:
            raise ValueError("minimum_size must not exceed maximum_size")
        if self.target_distribution.keys() != set(PortfolioCategory):
            raise ValueError("target_distribution must define every category")

        target_size = sum(
            target.target_count for target in self.target_distribution.values()
        )
        if not self.minimum_size <= target_size <= self.maximum_size:
            raise ValueError(
                "configured target counts must total within the size range"
            )
        return self


class LoadedPortfolioConfiguration(CoreModel):
    """Validated portfolio values paired with a content-derived version."""

    version: str
    values: PortfolioConfiguration


class UnmetPortfolioConstraint(CoreModel):
    """An explicit shortfall in the feasible portfolio."""

    code: PortfolioIssueCode
    category: PortfolioCategory | None
    required_count: int
    available_count: int


class PortfolioResult(CoreModel):
    """The best feasible balanced list and any balance shortfalls."""

    programs: list[ScoredProgramCandidate]
    unmet_constraints: list[UnmetPortfolioConstraint]
    configuration_version: str


_CAREER_ALIGNMENT_ORDER = tuple(CareerAlignment)
_CONFIDENCE_ORDER = tuple(Confidence)


def load_portfolio_configuration(
    config_path: Path = DEFAULT_PORTFOLIO_PATH,
    schema_path: Path = DEFAULT_PORTFOLIO_SCHEMA,
) -> LoadedPortfolioConfiguration:
    """Load and schema-validate the versioned portfolio distribution."""
    try:
        document = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(config_path.read_text(encoding="utf-8"))
        )
        schema = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        )
        if not isinstance(document, dict) or not isinstance(schema, dict):
            raise PortfolioConfigurationError(
                "portfolio and schema documents must be objects"
            )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
        values = PortfolioConfiguration.model_validate(document)
    except (
        OSError,
        PydanticValidationError,
        SchemaError,
        ValidationError,
        yaml.YAMLError,
    ) as error:
        raise PortfolioConfigurationError(
            f"Invalid portfolio configuration {config_path.name}: {error}"
        ) from error

    if values.provisional:
        warnings.warn(
            f"Provisional portfolio configuration: {values.version}",
            ProvisionalPortfolioWarning,
            stacklevel=2,
        )
    content_hash = sha256(config_path.read_bytes()).hexdigest()
    return LoadedPortfolioConfiguration(
        version=f"{values.version}:{content_hash}", values=values
    )


def build_portfolio(
    candidates: Sequence[ScoredProgramCandidate],
    constraints: StudentPortfolioConstraints,
    *,
    configuration: LoadedPortfolioConfiguration | None = None,
) -> PortfolioResult:
    """Build a constraint-respecting, category-balanced program list."""
    loaded = configuration or load_portfolio_configuration()
    _raise_on_duplicate_programs(candidates)
    feasible = [
        candidate
        for candidate in candidates
        if _meets_constraints(candidate, constraints)
    ]
    by_category = {
        category: [
            candidate for candidate in feasible if candidate.category is category
        ]
        for category in PortfolioCategory
    }

    selected: list[ScoredProgramCandidate] = []
    selected_ids: set[str] = set()
    for category in PortfolioCategory:
        target = loaded.values.target_distribution[category]
        for candidate in by_category[category][: target.target_count]:
            selected.append(candidate)
            selected_ids.add(candidate.program_id)

    desired_size = sum(
        target.target_count
        for target in loaded.values.target_distribution.values()
    )
    for candidate in feasible:
        if len(selected) >= desired_size:
            break
        if candidate.program_id in selected_ids:
            continue
        selected.append(candidate)
        selected_ids.add(candidate.program_id)

    selected = selected[: loaded.values.maximum_size]
    unmet = _unmet_constraints(selected, loaded.values)
    return PortfolioResult(
        programs=selected,
        unmet_constraints=unmet,
        configuration_version=loaded.version,
    )


def _meets_constraints(
    candidate: ScoredProgramCandidate,
    constraints: StudentPortfolioConstraints,
) -> bool:
    if constraints.maximum_annual_cost is not None and (
        candidate.annual_cost is None
        or candidate.annual_cost > constraints.maximum_annual_cost
    ):
        return False
    if constraints.funding_required and candidate.funding_available is not True:
        return False
    if constraints.allowed_locations and (
        candidate.location is None
        or _normalize(candidate.location)
        not in {_normalize(location) for location in constraints.allowed_locations}
    ):
        return False
    if constraints.minimum_career_alignment is not None and not _at_least(
        candidate.career_alignment,
        constraints.minimum_career_alignment,
        _CAREER_ALIGNMENT_ORDER,
    ):
        return False
    if constraints.minimum_data_confidence is not None and not _at_least(
        candidate.data_confidence,
        constraints.minimum_data_confidence,
        _CONFIDENCE_ORDER,
    ):
        return False
    return True


def _at_least(value: T, minimum: T, ordering: tuple[T, ...]) -> bool:
    return ordering.index(value) >= ordering.index(minimum)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _unmet_constraints(
    selected: Sequence[ScoredProgramCandidate],
    configuration: PortfolioConfiguration,
) -> list[UnmetPortfolioConstraint]:
    unmet: list[UnmetPortfolioConstraint] = []
    for category in PortfolioCategory:
        available = sum(candidate.category is category for candidate in selected)
        required = configuration.target_distribution[category].minimum_count
        if available < required:
            unmet.append(
                UnmetPortfolioConstraint(
                    code=PortfolioIssueCode.CATEGORY_MINIMUM_NOT_MET,
                    category=category,
                    required_count=required,
                    available_count=available,
                )
            )

    if len(selected) < configuration.minimum_size:
        unmet.append(
            UnmetPortfolioConstraint(
                code=PortfolioIssueCode.MINIMUM_PORTFOLIO_SIZE_NOT_MET,
                category=None,
                required_count=configuration.minimum_size,
                available_count=len(selected),
            )
        )
    return unmet


def _raise_on_duplicate_programs(
    candidates: Sequence[ScoredProgramCandidate],
) -> None:
    ids = [candidate.program_id for candidate in candidates]
    duplicates = sorted(
        {program_id for program_id in ids if ids.count(program_id) > 1}
    )
    if duplicates:
        raise PortfolioError("Duplicate program ids: " + ", ".join(duplicates))
