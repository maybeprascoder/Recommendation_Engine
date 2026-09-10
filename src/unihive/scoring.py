"""Deterministic readiness scoring, bands, confidence, and explanation traces.

Implements Build Spec sections 4 and 5.5 and Experience Doc section 4,
Principle 3.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Self

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import ConfigDict, HttpUrl, JsonValue, TypeAdapter, model_validator
from pydantic import ValidationError as PydanticValidationError

from unihive.models import (
    Assessment,
    AuditRecord,
    CoherenceRule,
    CompetencyLevel,
    CompetencyScoreTrace,
    Confidence,
    CoreModel,
    EligibilityStatus,
    EvidenceState,
    HardPrerequisiteFloorRule,
    ProfileShapeTrace,
    ProgramAlignment,
    ProgramConfig,
    ReadinessBand,
    ScoreExclusionReason,
    StudentCompetency,
)
from unihive.resources import DATA_ROOT

DEFAULT_BANDS_PATH = DATA_ROOT / "bands.yaml"
DEFAULT_BANDS_SCHEMA = DATA_ROOT / "schemas" / "bands.schema.json"
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class ScoringError(ValueError):
    """Raised when readiness cannot be evaluated from valid inputs."""


class ScoringConfigurationError(ScoringError):
    """Raised when readiness-band configuration is invalid."""


class ProvisionalScoringWarning(UserWarning):
    """Warns that unvalidated scoring configuration is in use."""


class ConfidenceConfiguration(CoreModel):
    """Demand-weighted evidence-state factors and categorical cutoffs."""

    state_factors: dict[EvidenceState, Decimal]
    cutoffs: dict[Confidence, Decimal]


class ScoringConfiguration(CoreModel):
    """All global, versioned values used by the scoring core."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    provisional: bool
    validated_by: str | None
    source: str | None
    score_ceiling: Decimal
    band_cutoffs: dict[ReadinessBand, Decimal]
    confidence: ConfidenceConfiguration

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        """Reject incomplete or non-monotonic band configuration."""
        if self.band_cutoffs.keys() != set(ReadinessBand):
            raise ValueError("band_cutoffs must define every ReadinessBand")
        ordered_bands = [self.band_cutoffs[band] for band in ReadinessBand]
        if ordered_bands != sorted(set(ordered_bands)):
            raise ValueError("readiness band cutoffs must be strictly increasing")
        if self.score_ceiling < ordered_bands[-1]:
            raise ValueError("score_ceiling must include the highest band cutoff")

        if self.confidence.state_factors.keys() != set(EvidenceState):
            raise ValueError("state_factors must define every EvidenceState")
        if self.confidence.cutoffs.keys() != set(Confidence):
            raise ValueError("confidence cutoffs must define every Confidence")
        ordered_confidence = [
            self.confidence.cutoffs[confidence] for confidence in Confidence
        ]
        if ordered_confidence != sorted(set(ordered_confidence)):
            raise ValueError("confidence cutoffs must be strictly increasing")
        return self


class LoadedScoringConfiguration(CoreModel):
    """Validated scoring values paired with their content-derived version."""

    version: str
    values: ScoringConfiguration


def load_scoring_configuration(
    bands_path: Path = DEFAULT_BANDS_PATH,
    schema_path: Path = DEFAULT_BANDS_SCHEMA,
) -> LoadedScoringConfiguration:
    """Load and schema-validate versioned readiness and confidence cutoffs."""
    try:
        document = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(bands_path.read_text(encoding="utf-8"))
        )
        schema = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        )
        if not isinstance(document, dict) or not isinstance(schema, dict):
            raise ScoringConfigurationError("band and schema documents must be objects")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
        values = ScoringConfiguration.model_validate(document)
    except (
        OSError,
        PydanticValidationError,
        SchemaError,
        ValidationError,
        yaml.YAMLError,
    ) as error:
        raise ScoringConfigurationError(
            f"Invalid scoring configuration {bands_path.name}: {error}"
        ) from error

    if values.provisional:
        warnings.warn(
            f"Provisional scoring configuration: {values.version}",
            ProvisionalScoringWarning,
            stacklevel=2,
        )
    content_hash = sha256(bands_path.read_bytes()).hexdigest()
    return LoadedScoringConfiguration(
        version=f"{values.version}:{content_hash}", values=values
    )


def score_assessment(
    competencies: Sequence[StudentCompetency],
    program: ProgramConfig,
    *,
    taxonomy_version: str,
    engine_version: str,
    timestamp: datetime,
    eligibility: EligibilityStatus = EligibilityStatus.UNKNOWN,
    preference_fit: JsonValue = None,
    admissions_outlook: JsonValue = None,
    configuration: LoadedScoringConfiguration | None = None,
) -> Assessment:
    """Produce the six separate assessment reads and full scoring trace."""
    loaded = configuration or load_scoring_configuration()
    competency_by_id = _index_competencies(competencies)
    traces: list[CompetencyScoreTrace] = []
    not_assessed: list[str] = []
    contribution_sum = Decimal("0")
    known_demand_weight = Decimal("0")
    configured_demand_weight = Decimal("0")

    for competency_id, demand in sorted(program.demand_profile.items()):
        configured_demand_weight += demand.weight
        competency = competency_by_id.get(competency_id)
        state = competency.state if competency is not None else EvidenceState.UNKNOWN
        level = competency.level if competency is not None else None
        evidence_ids = (
            competency.contributing_evidence_ids if competency is not None else []
        )
        evidence_trace = competency.explanation_trace if competency is not None else []

        if state is EvidenceState.UNKNOWN or (
            state in _present_states() and level is None
        ):
            not_assessed.append(competency_id)
            traces.append(
                CompetencyScoreTrace(
                    competency_id=competency_id,
                    state=state,
                    demonstrated_level=level,
                    expected_level=demand.required_level,
                    demand_weight=demand.weight,
                    match_value=None,
                    contribution=None,
                    evidence_ids=evidence_ids,
                    evidence_trace=evidence_trace,
                    exclusion_reason=ScoreExclusionReason.UNKNOWN,
                )
            )
            continue

        if state is EvidenceState.NOT_APPLICABLE:
            traces.append(
                CompetencyScoreTrace(
                    competency_id=competency_id,
                    state=state,
                    demonstrated_level=level,
                    expected_level=demand.required_level,
                    demand_weight=demand.weight,
                    match_value=None,
                    contribution=None,
                    evidence_ids=evidence_ids,
                    evidence_trace=evidence_trace,
                    exclusion_reason=ScoreExclusionReason.NOT_APPLICABLE,
                )
            )
            continue

        known_demand_weight += demand.weight
        if competency is None:
            raise ScoringError("Known scoring state has no competency record")
        match_value = _match_value(competency, demand.required_level, loaded.values)
        contribution = demand.weight * match_value
        contribution_sum += contribution
        traces.append(
            CompetencyScoreTrace(
                competency_id=competency_id,
                state=state,
                demonstrated_level=level,
                expected_level=demand.required_level,
                demand_weight=demand.weight,
                match_value=match_value,
                contribution=contribution,
                evidence_ids=evidence_ids,
                evidence_trace=evidence_trace,
                exclusion_reason=None,
            )
        )

    base_readiness = (
        contribution_sum / known_demand_weight
        if known_demand_weight > Decimal("0")
        else None
    )
    readiness, shape_trace, band_caps = _apply_profile_shape_rules(
        base_readiness,
        competency_by_id,
        program,
        loaded.values,
    )
    band = _band_for(readiness, loaded.values)
    band = _apply_band_caps(band, band_caps, loaded.values)
    confidence = _data_confidence(
        competency_by_id, program, loaded.values
    )

    used_evidence_ids = sorted(
        {
            evidence_id
            for trace in traces
            if trace.exclusion_reason is None
            for evidence_id in trace.evidence_ids
        }
    )
    source_urls = _source_urls(program)
    audit = AuditRecord(
        engine_version=engine_version,
        taxonomy_version=taxonomy_version,
        program_config_version=program.version,
        evidence_ids_used=used_evidence_ids,
        missing_fields=not_assessed,
        source_urls=source_urls,
        timestamp=timestamp,
        confidence=confidence,
        scoring_config_version=loaded.version,
    )
    alignment = ProgramAlignment(
        readiness_value=readiness,
        base_readiness_value=base_readiness,
        contribution_sum=contribution_sum,
        known_demand_weight=known_demand_weight,
        configured_demand_weight=configured_demand_weight,
        competency_trace=traces,
        profile_shape_trace=shape_trace,
        band_config_version=loaded.version,
    )
    return Assessment(
        pathway_readiness=band,
        program_alignment=alignment,
        eligibility=eligibility,
        preference_fit=preference_fit,
        admissions_outlook=admissions_outlook,
        data_confidence=confidence,
        audit=audit,
        not_assessed=not_assessed,
    )


def score(
    competencies: Sequence[StudentCompetency],
    program: ProgramConfig,
    *,
    taxonomy_version: str,
    engine_version: str,
    timestamp: datetime,
    eligibility: EligibilityStatus = EligibilityStatus.UNKNOWN,
    preference_fit: JsonValue = None,
    admissions_outlook: JsonValue = None,
    configuration: LoadedScoringConfiguration | None = None,
) -> Assessment:
    """Concise public name for ``score_assessment``."""
    return score_assessment(
        competencies,
        program,
        taxonomy_version=taxonomy_version,
        engine_version=engine_version,
        timestamp=timestamp,
        eligibility=eligibility,
        preference_fit=preference_fit,
        admissions_outlook=admissions_outlook,
        configuration=configuration,
    )


def _match_value(
    competency: StudentCompetency,
    expected_level: CompetencyLevel,
    configuration: ScoringConfiguration,
) -> Decimal:
    if competency.state is EvidenceState.CONFIRMED_ABSENT:
        return Decimal("0")
    if competency.level is None:
        raise ScoringError(
            f"Known competency {competency.competency_id} has no level"
        )
    ratio = Decimal(competency.level.value) / Decimal(expected_level.value)
    return min(ratio, configuration.score_ceiling)


def _data_confidence(
    competency_by_id: dict[str, StudentCompetency],
    program: ProgramConfig,
    configuration: ScoringConfiguration,
) -> Confidence:
    weighted_confidence = Decimal("0")
    demand_weight = Decimal("0")
    for competency_id, demand in sorted(program.demand_profile.items()):
        competency = competency_by_id.get(competency_id)
        state = competency.state if competency is not None else EvidenceState.UNKNOWN
        if (
            competency is not None
            and state in _present_states()
            and competency.level is None
        ):
            state = EvidenceState.UNKNOWN
        weighted_confidence += (
            demand.weight * configuration.confidence.state_factors[state]
        )
        demand_weight += demand.weight

    value = (
        weighted_confidence / demand_weight
        if demand_weight > Decimal("0")
        else configuration.confidence.cutoffs[Confidence.LOW]
    )
    for confidence in reversed(Confidence):
        if value >= configuration.confidence.cutoffs[confidence]:
            return confidence
    raise ScoringConfigurationError("confidence value is below every cutoff")


def _apply_profile_shape_rules(
    readiness: Decimal | None,
    competency_by_id: dict[str, StudentCompetency],
    program: ProgramConfig,
    configuration: ScoringConfiguration,
) -> tuple[Decimal | None, list[ProfileShapeTrace], list[ReadinessBand]]:
    adjusted = readiness
    traces: list[ProfileShapeTrace] = []
    band_caps: list[ReadinessBand] = []

    for rule in program.profile_shape_rules:
        if isinstance(rule, HardPrerequisiteFloorRule):
            competency = competency_by_id.get(rule.competency_id)
            applied = competency is not None and (
                competency.state is EvidenceState.CONFIRMED_ABSENT
                or (
                    competency.state in _present_states()
                    and competency.level is not None
                    and competency.level < rule.minimum_level
                )
            )
            if applied:
                band_caps.append(rule.maximum_band)
            traces.append(
                ProfileShapeTrace(
                    rule_id=rule.id,
                    rule_type=rule.type,
                    applied=applied,
                    rationale=rule.rationale,
                    adjustment=None,
                    band_cap=rule.maximum_band if applied else None,
                )
            )
            continue

        if isinstance(rule, CoherenceRule):
            demonstrated = sum(
                competency is not None
                and competency.state in _present_states()
                and competency.level is not None
                and competency.level >= rule.minimum_level
                for competency in (
                    competency_by_id.get(competency_id)
                    for competency_id in rule.competency_ids
                )
            )
            applied = adjusted is not None and demonstrated >= rule.minimum_count
            if applied and adjusted is not None:
                adjusted = _clamp_readiness(
                    adjusted + rule.adjustment, configuration
                )
            traces.append(
                ProfileShapeTrace(
                    rule_id=rule.id,
                    rule_type=rule.type,
                    applied=applied,
                    rationale=rule.rationale,
                    adjustment=rule.adjustment if applied else None,
                    band_cap=None,
                )
            )
            continue

        raise TypeError(f"Unsupported profile-shape rule: {type(rule).__name__}")

    return adjusted, traces, band_caps


def _clamp_readiness(
    value: Decimal, configuration: ScoringConfiguration
) -> Decimal:
    floor = configuration.band_cutoffs[ReadinessBand.EMERGING]
    return min(max(value, floor), configuration.score_ceiling)


def _band_for(
    readiness: Decimal | None, configuration: ScoringConfiguration
) -> ReadinessBand | None:
    if readiness is None:
        return None
    for band in reversed(ReadinessBand):
        if readiness >= configuration.band_cutoffs[band]:
            return band
    raise ScoringConfigurationError("readiness value is below every band cutoff")


def _apply_band_caps(
    band: ReadinessBand | None,
    caps: Sequence[ReadinessBand],
    configuration: ScoringConfiguration,
) -> ReadinessBand | None:
    if band is None or not caps:
        return band
    strictest_cap = min(caps, key=configuration.band_cutoffs.__getitem__)
    if configuration.band_cutoffs[band] > configuration.band_cutoffs[strictest_cap]:
        return strictest_cap
    return band


def _index_competencies(
    competencies: Sequence[StudentCompetency],
) -> dict[str, StudentCompetency]:
    indexed: dict[str, StudentCompetency] = {}
    for competency in competencies:
        if competency.competency_id in indexed:
            raise ScoringError(
                f"Duplicate student competency: {competency.competency_id}"
            )
        indexed[competency.competency_id] = competency
    return indexed


def _source_urls(program: ProgramConfig) -> list[HttpUrl]:
    urls = [program.source_url]
    urls.extend(rule.source_url for rule in program.eligibility_rules)
    urls.extend(rule.source_url for rule in program.profile_shape_rules)
    return list({str(url): url for url in sorted(urls, key=str)}.values())


def _present_states() -> set[EvidenceState]:
    return {
        EvidenceState.VERIFIED_PRESENT,
        EvidenceState.SELF_REPORTED_PRESENT,
    }
