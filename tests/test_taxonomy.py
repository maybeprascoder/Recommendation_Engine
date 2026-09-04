"""Tests for taxonomy schema validation, integrity, lookup, and versioning."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from unihive.taxonomy import (
    DEFAULT_SCHEMA_DIR,
    ProvisionalTaxonomyWarning,
    Taxonomy,
    TaxonomyCycleError,
    TaxonomyIntegrityError,
    TaxonomySchemaError,
    load_taxonomy,
)

WriteTaxonomy = Callable[[str], None]


@pytest.fixture
def taxonomy_dir(tmp_path: Path) -> Path:
    """Create the non-competency files shared by taxonomy test cases."""
    (tmp_path / "aliases.yaml").write_text(
        "aliases:\n  nets: networking\n", encoding="utf-8"
    )
    (tmp_path / "evidence_rules.yaml").write_text("rules: []\n", encoding="utf-8")
    shutil.copyfile(
        DEFAULT_SCHEMA_DIR.parent / "taxonomy" / "ladders.yaml",
        tmp_path / "ladders.yaml",
    )
    return tmp_path


@pytest.fixture
def write_taxonomy(taxonomy_dir: Path) -> WriteTaxonomy:
    """Return a helper that writes a competencies document around YAML items."""

    def write(items: str) -> None:
        (taxonomy_dir / "competencies.yaml").write_text(
            f"competencies:\n{items}", encoding="utf-8"
        )

    return write


def node_yaml(
    competency_id: str,
    *,
    parent_ids: str = "[]",
    child_ids: str = "[]",
    name: str | None = None,
) -> str:
    """Build one complete YAML node with configurable relationships."""
    display_name = name or competency_id.replace("_", " ").title()
    return (
        f"  - id: {competency_id}\n"
        f"    name: {display_name}\n"
        "    fields: []\n"
        f"    parent_ids: {parent_ids}\n"
        f"    child_ids: {child_ids}\n"
        "    cip_anchor: null\n"
        "    description: Test competency.\n"
        "    provisional: true\n"
        "    validated_by: null\n"
        "    source: test\n"
    )


def load_test_taxonomy(taxonomy_dir: Path) -> Taxonomy:
    """Load a test taxonomy while asserting its required provisional warning."""
    with pytest.warns(ProvisionalTaxonomyWarning):
        return load_taxonomy(taxonomy_dir, DEFAULT_SCHEMA_DIR)


def test_valid_file_loads(taxonomy_dir: Path, write_taxonomy: WriteTaxonomy) -> None:
    write_taxonomy(node_yaml("networking"))

    taxonomy = load_test_taxonomy(taxonomy_dir)

    assert taxonomy.lookup_by_id("networking").name == "Networking"


def test_malformed_file_raises(
    taxonomy_dir: Path, write_taxonomy: WriteTaxonomy
) -> None:
    write_taxonomy("  - id: missing_required_fields\n")

    with pytest.raises(TaxonomySchemaError):
        load_taxonomy(taxonomy_dir, DEFAULT_SCHEMA_DIR)


def test_cycle_raises(taxonomy_dir: Path, write_taxonomy: WriteTaxonomy) -> None:
    write_taxonomy(
        node_yaml("first", parent_ids="[second]")
        + node_yaml("second", parent_ids="[first]")
    )

    with pytest.raises(TaxonomyCycleError):
        load_taxonomy(taxonomy_dir, DEFAULT_SCHEMA_DIR)


def test_dangling_reference_raises(
    taxonomy_dir: Path, write_taxonomy: WriteTaxonomy
) -> None:
    write_taxonomy(node_yaml("networking", parent_ids="[missing]"))

    with pytest.raises(TaxonomyIntegrityError, match="missing"):
        load_taxonomy(taxonomy_dir, DEFAULT_SCHEMA_DIR)


def test_alias_lookup_resolves(
    taxonomy_dir: Path, write_taxonomy: WriteTaxonomy
) -> None:
    write_taxonomy(node_yaml("networking"))

    taxonomy = load_test_taxonomy(taxonomy_dir)

    assert taxonomy.lookup_by_alias(" NETS ").id == "networking"


def test_version_hash_is_stable_and_content_sensitive(
    taxonomy_dir: Path, write_taxonomy: WriteTaxonomy
) -> None:
    write_taxonomy(node_yaml("networking"))
    first = load_test_taxonomy(taxonomy_dir).version
    second = load_test_taxonomy(taxonomy_dir).version

    aliases_path = taxonomy_dir / "aliases.yaml"
    aliases_path.write_text(
        aliases_path.read_text(encoding="utf-8") + "  network: networking\n",
        encoding="utf-8",
    )
    changed = load_test_taxonomy(taxonomy_dir).version

    assert first == second
    assert changed != first


def test_seed_taxonomy_loads() -> None:
    """Keep the checked-in taxonomy and schemas compatible."""
    seed_dir = DEFAULT_SCHEMA_DIR.parent / "taxonomy"
    with pytest.warns(ProvisionalTaxonomyWarning) as warning_records:
        taxonomy = load_taxonomy(seed_dir, DEFAULT_SCHEMA_DIR)

    warning_text = str(warning_records[0].message)
    assert all(node.id in warning_text for node in taxonomy.competencies)
