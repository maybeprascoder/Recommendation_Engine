"""Load and validate the versioned competency taxonomy.

Implements Build Spec sections 3 and 4 -- the shared competency layer and its
program-independent evidence mappings.
"""

from __future__ import annotations

import warnings
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, model_validator
from pydantic import ValidationError as PydanticValidationError

from unihive.resources import DATA_ROOT
from unihive.understanding import load_evaluation_rubric

DEFAULT_TAXONOMY_DIR = DATA_ROOT / "taxonomy"
DEFAULT_SCHEMA_DIR = DATA_ROOT / "schemas"
UNDERSTANDING_TAXONOMY_FILES: tuple[tuple[str, str], ...] = (
    ("aliases.yaml", "aliases.schema.json"),
    ("competencies.yaml", "competencies.schema.json"),
    ("evidence_rules.yaml", "evidence_rules.schema.json"),
    ("ladders.yaml", "ladders.schema.json"),
)
TAXONOMY_FILES: tuple[tuple[str, str], ...] = (
    *UNDERSTANDING_TAXONOMY_FILES,
    ("qualitative_mappings.yaml", "qualitative_mappings.schema.json"),
)
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class TaxonomyError(ValueError):
    """Base error raised when taxonomy data cannot be loaded safely."""


class TaxonomySchemaError(TaxonomyError):
    """Raised when a taxonomy document does not satisfy its JSON Schema."""


class TaxonomyIntegrityError(TaxonomyError):
    """Raised when references or graph relationships are invalid."""


class TaxonomyCycleError(TaxonomyIntegrityError):
    """Raised when competency relationships contain a directed cycle."""


class ProvisionalTaxonomyWarning(UserWarning):
    """Warns that unvalidated competency nodes are present."""


class CompetencyNode(BaseModel):
    """One sourced node in the shared competency taxonomy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    fields: tuple[str, ...]
    parent_ids: tuple[str, ...]
    child_ids: tuple[str, ...]
    cip_anchor: str | None
    description: str
    provisional: bool
    validated_by: str | None
    source: str | None


class EvidenceRule(BaseModel):
    """A provisional, program-independent evidence mapping rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    evidence_kind: str
    competency_id: str
    quality_ladder: str
    relevance: Decimal
    provisional: bool
    validated_by: str | None
    source: str | None


class JudgmentRequirement(BaseModel):
    """One reviewed qualitative condition required by an approved mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: str
    labels: tuple[str, ...]


class QualitativeEvidenceMapping(BaseModel):
    """System configuration, optionally provisional, never per-student approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    claim_category: str
    rubric_sha256: str
    judgment_requirements: tuple[JudgmentRequirement, ...]
    evidence_rule_id: str
    quality_label: str
    depth_label: str
    provisional: bool = False
    priority: int = 0
    validated_by: str | None
    validated_on: date | None
    source: str | None

    @model_validator(mode="after")
    def require_validation_for_calibrated_mapping(self) -> QualitativeEvidenceMapping:
        if not self.provisional and not (
            self.validated_by and self.validated_on and self.source
        ):
            raise ValueError("Non-provisional mappings require validation metadata")
        return self


class Taxonomy(BaseModel):
    """An immutable taxonomy snapshot with deterministic lookup helpers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    understanding_version: str
    competencies: tuple[CompetencyNode, ...]
    aliases: dict[str, str]
    evidence_rules: tuple[EvidenceRule, ...]
    evidence_configuration: dict[str, JsonValue]
    qualitative_mapping_version: str
    qualitative_mappings: tuple[QualitativeEvidenceMapping, ...]

    def lookup_by_id(self, competency_id: str) -> CompetencyNode:
        """Return a competency by canonical id, raising ``KeyError`` if absent."""
        for competency in self.competencies:
            if competency.id == competency_id:
                return competency
        raise KeyError(competency_id)

    def lookup_by_alias(self, alias: str) -> CompetencyNode:
        """Resolve a case-insensitive alias to its competency node."""
        normalized_alias = _normalize_alias(alias)
        try:
            competency_id = self.aliases[normalized_alias]
        except KeyError as error:
            raise KeyError(alias) from error
        return self.lookup_by_id(competency_id)


def load_taxonomy(
    taxonomy_dir: Path = DEFAULT_TAXONOMY_DIR,
    schema_dir: Path = DEFAULT_SCHEMA_DIR,
) -> Taxonomy:
    """Load, schema-validate, integrity-check, and version taxonomy files."""
    documents = {
        data_name: _load_validated_document(
            taxonomy_dir / data_name, schema_dir / schema_name
        )
        for data_name, schema_name in TAXONOMY_FILES
    }

    competencies = _parse_competencies(documents["competencies.yaml"])
    competency_ids = {competency.id for competency in competencies}
    _validate_relationships(competencies, competency_ids)
    aliases = _parse_aliases(documents["aliases.yaml"], competency_ids)
    evidence_rules = _parse_evidence_rules(
        documents["evidence_rules.yaml"], competency_ids
    )
    mapping_version, qualitative_mappings = _parse_qualitative_mappings(
        documents["qualitative_mappings.yaml"],
        evidence_rules,
        documents["ladders.yaml"],
    )

    provisional_ids = sorted(
        competency.id for competency in competencies if competency.provisional
    )
    if provisional_ids:
        warnings.warn(
            "Provisional competency nodes: " + ", ".join(provisional_ids),
            ProvisionalTaxonomyWarning,
            stacklevel=2,
        )
    provisional_records: tuple[EvidenceRule | QualitativeEvidenceMapping, ...] = (
        *evidence_rules,
        *qualitative_mappings,
    )
    for record in provisional_records:
        if record.provisional:
            warnings.warn(
                f"Provisional scoring configuration: {record.id}",
                ProvisionalTaxonomyWarning,
                stacklevel=2,
            )
    if documents["ladders.yaml"].get("provisional") is True:
        warnings.warn(
            "Provisional scoring configuration: ladders.yaml",
            ProvisionalTaxonomyWarning,
            stacklevel=2,
        )

    return Taxonomy(
        version=_content_version(taxonomy_dir),
        understanding_version=_content_version(
            taxonomy_dir, UNDERSTANDING_TAXONOMY_FILES
        ),
        competencies=competencies,
        aliases=aliases,
        evidence_rules=evidence_rules,
        evidence_configuration=documents["ladders.yaml"],
        qualitative_mapping_version=mapping_version,
        qualitative_mappings=qualitative_mappings,
    )


def _load_validated_document(
    data_path: Path, schema_path: Path
) -> dict[str, JsonValue]:
    try:
        document = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(data_path.read_text(encoding="utf-8"))
        )
        schema = JSON_VALUE_ADAPTER.validate_python(
            yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        )
        if not isinstance(document, dict) or not isinstance(schema, dict):
            raise TaxonomySchemaError(f"{data_path.name} must contain an object")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
    except (
        OSError,
        PydanticValidationError,
        SchemaError,
        ValidationError,
        yaml.YAMLError,
    ) as error:
        raise TaxonomySchemaError(
            f"Invalid taxonomy file {data_path.name}: {error}"
        ) from error
    return document


def _parse_competencies(
    document: dict[str, JsonValue],
) -> tuple[CompetencyNode, ...]:
    raw_competencies = document["competencies"]
    if not isinstance(raw_competencies, list):
        raise TaxonomySchemaError("competencies must be an array")

    try:
        competencies = tuple(
            CompetencyNode.model_validate(raw_competency)
            for raw_competency in raw_competencies
        )
    except PydanticValidationError as error:
        raise TaxonomySchemaError(f"Invalid competency node: {error}") from error

    ids = [competency.id for competency in competencies]
    duplicates = sorted(
        {competency_id for competency_id in ids if ids.count(competency_id) > 1}
    )
    if duplicates:
        raise TaxonomyIntegrityError(
            "Duplicate competency ids: " + ", ".join(duplicates)
        )
    return competencies


def _validate_relationships(
    competencies: tuple[CompetencyNode, ...], competency_ids: set[str]
) -> None:
    graph = {competency.id: set(competency.child_ids) for competency in competencies}
    dangling: set[str] = set()

    for competency in competencies:
        for parent_id in competency.parent_ids:
            if parent_id not in competency_ids:
                dangling.add(parent_id)
            else:
                graph[parent_id].add(competency.id)
        dangling.update(
            child_id
            for child_id in competency.child_ids
            if child_id not in competency_ids
        )

    if dangling:
        raise TaxonomyIntegrityError(
            "Dangling competency references: " + ", ".join(sorted(dangling))
        )
    _raise_on_cycle(graph)


def _raise_on_cycle(graph: dict[str, set[str]]) -> None:
    visited: set[str] = set()
    active: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in active:
            raise TaxonomyCycleError(f"Competency relationship cycle at {node_id}")
        if node_id in visited:
            return

        active.add(node_id)
        for child_id in sorted(graph[node_id]):
            visit(child_id)
        active.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(graph):
        visit(node_id)


def _parse_aliases(
    document: dict[str, JsonValue], competency_ids: set[str]
) -> dict[str, str]:
    raw_aliases = document["aliases"]
    if not isinstance(raw_aliases, dict):
        raise TaxonomySchemaError("aliases must be an object")

    aliases: dict[str, str] = {}
    dangling: set[str] = set()
    for alias, target in raw_aliases.items():
        if not isinstance(alias, str) or not isinstance(target, str):
            raise TaxonomySchemaError("aliases must map strings to competency ids")
        normalized_alias = _normalize_alias(alias)
        if normalized_alias in aliases:
            raise TaxonomyIntegrityError(f"Duplicate normalized alias: {alias}")
        aliases[normalized_alias] = target
        if target not in competency_ids:
            dangling.add(target)

    if dangling:
        raise TaxonomyIntegrityError(
            "Dangling alias targets: " + ", ".join(sorted(dangling))
        )
    return aliases


def _parse_evidence_rules(
    document: dict[str, JsonValue], competency_ids: set[str]
) -> tuple[EvidenceRule, ...]:
    raw_rules = document["rules"]
    if not isinstance(raw_rules, list):
        raise TaxonomySchemaError("rules must be an array")

    try:
        rules = tuple(EvidenceRule.model_validate(rule) for rule in raw_rules)
    except PydanticValidationError as error:
        raise TaxonomySchemaError(f"Invalid evidence rule: {error}") from error

    ids = [rule.id for rule in rules]
    duplicate_ids = sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1})
    if duplicate_ids:
        raise TaxonomyIntegrityError(
            "Duplicate evidence-rule ids: " + ", ".join(duplicate_ids)
        )

    pairs = [(rule.evidence_kind, rule.competency_id) for rule in rules]
    duplicate_pairs = sorted({pair for pair in pairs if pairs.count(pair) > 1})
    if duplicate_pairs:
        formatted_pairs = [
            f"{kind}->{competency}" for kind, competency in duplicate_pairs
        ]
        raise TaxonomyIntegrityError(
            "Duplicate evidence-rule mappings: " + ", ".join(formatted_pairs)
        )

    dangling = {
        rule.competency_id for rule in rules if rule.competency_id not in competency_ids
    }
    if dangling:
        raise TaxonomyIntegrityError(
            "Dangling evidence-rule targets: " + ", ".join(sorted(dangling))
        )
    return rules


def _parse_qualitative_mappings(
    document: dict[str, JsonValue],
    evidence_rules: tuple[EvidenceRule, ...],
    evidence_configuration: dict[str, JsonValue],
) -> tuple[str, tuple[QualitativeEvidenceMapping, ...]]:
    """Validate system mappings and all deterministic inputs, including seeds."""
    raw_version = document["version"]
    raw_mappings = document["mappings"]
    if not isinstance(raw_version, str) or not isinstance(raw_mappings, list):
        raise TaxonomySchemaError("qualitative mappings need a version and array")
    try:
        mappings = tuple(
            QualitativeEvidenceMapping.model_validate(item) for item in raw_mappings
        )
    except PydanticValidationError as error:
        raise TaxonomySchemaError(f"Invalid qualitative mapping: {error}") from error
    ids = [mapping.id for mapping in mappings]
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    if duplicate_ids:
        raise TaxonomyIntegrityError(
            "Duplicate qualitative-mapping ids: " + ", ".join(duplicate_ids)
        )
    rules = {rule.id: rule for rule in evidence_rules}
    raw_ladders = evidence_configuration.get("quality_ladders")
    raw_depths = evidence_configuration.get("depth_factors")
    assert isinstance(raw_ladders, dict) and isinstance(raw_depths, dict)
    rubric_labels = {
        item.id: set(item.labels) - {"unknown"}
        for item in load_evaluation_rubric().dimensions
    }
    priorities: set[tuple[str, str, int]] = set()
    for mapping in mappings:
        dimensions = [item.dimension for item in mapping.judgment_requirements]
        if len(set(dimensions)) != len(dimensions):
            raise TaxonomyIntegrityError(
                f"Duplicate judgment dimension in mapping {mapping.id}"
            )
        if any(
            not set(item.labels).issubset(rubric_labels.get(item.dimension, set()))
            for item in mapping.judgment_requirements
        ):
            raise TaxonomyIntegrityError(
                f"Mapping {mapping.id} has unknown rubric labels"
            )
        try:
            rule = rules[mapping.evidence_rule_id]
            ladder = raw_ladders[rule.quality_ladder]
        except KeyError as error:
            raise TaxonomyIntegrityError(
                f"Mapping {mapping.id} references an unknown scoring input"
            ) from error
        if not mapping.provisional and (
            rule.provisional or not rule.validated_by or not rule.source
        ):
            raise TaxonomyIntegrityError(
                f"Mapping {mapping.id} requires an expert-validated evidence rule"
            )
        priority_key = (mapping.claim_category, rule.competency_id, mapping.priority)
        if priority_key in priorities:
            raise TaxonomyIntegrityError(
                "Mapping priorities must be unique per category/competency"
            )
        priorities.add(priority_key)
        if not isinstance(ladder, dict) or mapping.quality_label not in ladder:
            raise TaxonomyIntegrityError(
                f"Mapping {mapping.id} has an unknown quality label"
            )
        if mapping.depth_label not in raw_depths:
            raise TaxonomyIntegrityError(
                f"Mapping {mapping.id} has an unknown depth label"
            )
    return raw_version, mappings


def _normalize_alias(alias: str) -> str:
    return " ".join(alias.casefold().split())


def _content_version(
    taxonomy_dir: Path,
    files: tuple[tuple[str, str], ...] = TAXONOMY_FILES,
) -> str:
    digest = sha256()
    for data_name, _ in files:
        payload = (taxonomy_dir / data_name).read_bytes()
        digest.update(data_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()
