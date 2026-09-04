"""Tests for deterministic, program-independent competency resolution."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from unihive.competency import resolve_competencies
from unihive.models import (
    Confidence,
    Evidence,
    EvidenceState,
    StudentCompetency,
    StudentProfile,
)
from unihive.taxonomy import ProvisionalTaxonomyWarning, Taxonomy, load_taxonomy

AS_OF = date(2026, 1, 1)


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    """Load the checked-in provisional taxonomy once for resolution tests."""
    with pytest.warns(ProvisionalTaxonomyWarning):
        return load_taxonomy()


def profile_with(evidence: list[Evidence]) -> StudentProfile:
    """Build the narrowest complete profile needed by competency resolution."""
    return StudentProfile(
        academic_history=[],
        normalized_gpa=None,
        courses=[],
        skills=[],
        projects=[],
        research=[],
        work=[],
        goals=[],
        constraints=[],
        tests=[],
        evidence=evidence,
    )


def publication(
    evidence_id: str,
    *,
    state: EvidenceState = EvidenceState.VERIFIED_PRESENT,
    quality: str | None = "preprint",
    depth: str | None = "unspecified",
) -> Evidence:
    """Create machine-learning publication evidence for a test profile."""
    return Evidence(
        id=evidence_id,
        kind="machine_learning_publication",
        raw_text="Structured test evidence",
        state=state,
        quality=quality,
        depth=depth,
        recency=date(2025, 12, 1),
        source="test",
        extraction_confidence=Confidence.HIGH,
    )


def ml_result(results: list[StudentCompetency]) -> StudentCompetency:
    """Select the machine-learning result from a complete resolution."""
    return next(item for item in results if item.competency_id == "machine_learning")


def test_one_top_first_author_paper_outranks_two_preprints(
    taxonomy: Taxonomy,
) -> None:
    top_paper = profile_with(
        [publication("top", quality="top_tier_venue", depth="first_author")]
    )
    two_preprints = profile_with(
        [publication("preprint-1"), publication("preprint-2")]
    )

    top_level = ml_result(
        resolve_competencies(top_paper, taxonomy, as_of=AS_OF)
    ).level
    preprint_level = ml_result(
        resolve_competencies(two_preprints, taxonomy, as_of=AS_OF)
    ).level

    assert top_level is not None
    assert preprint_level is not None
    assert top_level > preprint_level


def test_unknown_stays_unknown(taxonomy: Taxonomy) -> None:
    result = ml_result(
        resolve_competencies(profile_with([]), taxonomy, as_of=AS_OF)
    )

    assert result.state is EvidenceState.UNKNOWN
    assert result.level is None
    assert result.explanation_trace == []


def test_confirmed_absent_is_distinct_from_unknown(taxonomy: Taxonomy) -> None:
    absent = ml_result(
        resolve_competencies(
            profile_with(
                [
                    publication(
                        "absent",
                        state=EvidenceState.CONFIRMED_ABSENT,
                        quality=None,
                        depth=None,
                    )
                ]
            ),
            taxonomy,
            as_of=AS_OF,
        )
    )
    unknown = ml_result(
        resolve_competencies(profile_with([]), taxonomy, as_of=AS_OF)
    )

    assert absent.state is EvidenceState.CONFIRMED_ABSENT
    assert absent.level is None
    assert absent.explanation_trace[0].contribution is None
    assert unknown.state is EvidenceState.UNKNOWN
    assert absent.state is not unknown.state


def test_resolution_is_deterministic_across_100_runs(taxonomy: Taxonomy) -> None:
    profile = profile_with(
        [
            publication("top", quality="top_tier_venue", depth="first_author"),
            publication("preprint"),
        ]
    )

    serialized = {
        tuple(
            item.model_dump_json()
            for item in resolve_competencies(profile, taxonomy, as_of=AS_OF)
        )
        for _ in range(100)
    }

    assert len(serialized) == 1


def test_explanation_trace_records_each_attribute(taxonomy: Taxonomy) -> None:
    result = ml_result(
        resolve_competencies(
            profile_with(
                [publication("top", quality="top_tier_venue", depth="first_author")]
            ),
            taxonomy,
            as_of=AS_OF,
        )
    )

    trace = result.explanation_trace[0]
    assert trace.evidence_id == "top"
    assert trace.quality is not None
    assert trace.relevance is not None
    assert trace.depth is not None
    assert trace.verification is not None
    assert trace.recency is not None
    assert trace.combination_multiplier is not None
    assert trace.contribution is not None


def test_competency_module_has_no_program_or_demand_imports() -> None:
    path = Path(__file__).parents[1] / "src" / "unihive" / "competency.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    referenced_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    forbidden = {"CompetencyDemand", "ProgramConfig", "demand_profile"}
    assert not forbidden & imported_names
    assert not forbidden & referenced_names
    assert not forbidden & referenced_attributes
