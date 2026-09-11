"""Generic confirmation preserves provenance and cannot confer scoring credit."""

import json
from datetime import date
from pathlib import Path

import pytest
from understanding_samples import mixed_result

from unihive.competency import resolve_competencies
from unihive.evidence import (
    EvidenceValueError,
    evaluate_evidence,
    load_evidence_configuration,
)
from unihive.models import EvidenceState, StudentProfile
from unihive.review import ConfirmationRequest, EvidenceCorrection, confirm_evidence
from unihive.taxonomy import load_taxonomy
from unihive.understanding import UnderstandingResult
from unihive.understanding_review import (
    ClaimDecision,
    confirm_understanding,
    initial_claim_corrections,
    validate_understanding,
)


def empty_profile() -> StudentProfile:
    data = json.loads((Path(__file__).parent / "fixtures/cli/profile.json").read_text())
    data.update(evidence=[], academic_history=[], normalized_gpa=None)
    return StudentProfile.model_validate(data)


def test_canonical_student_claims_only_and_no_academic_conversion() -> None:
    result = mixed_result()
    changes = initial_claim_corrections(result)
    # Even explicitly confirming everything cannot promote rejected claims.
    changes = [
        change.model_copy(update={"decision": ClaimDecision.CONFIRM})
        for change in changes
    ]
    profile = confirm_understanding(
        empty_profile(), result, changes, result.audit.taxonomy_version
    )
    assert len(profile.evidence) == 2
    assert [item.kind for item in profile.evidence] == ["project", "education"]
    assert all(
        item.state == EvidenceState.SELF_REPORTED_PRESENT
        and item.quality is None
        and item.depth is None
        and item.scoring_exclusion == "awaiting_approved_mapping"
        for item in profile.evidence
    )
    assert "学生" in profile.evidence[0].source
    assert profile.normalized_gpa is None and profile.academic_history == []
    assert result.draft.academics[0].grade_scale == "10"
    assert (
        confirm_understanding(profile, result, changes, result.audit.taxonomy_version)
        == profile
    )


@pytest.mark.parametrize(
    "edit",
    [
        {"statement": "I independently built everything."},
        {"attribution": "team"},
        {"decision": "uncertain"},
        {"decision": "exclude"},
    ],
)
def test_corrections_cannot_bypass_support_review(edit: dict) -> None:
    result = mixed_result()
    changes = initial_claim_corrections(result)
    changes[0] = type(changes[0]).model_validate({**changes[0].model_dump(), **edit})
    profile = confirm_understanding(
        empty_profile(), result, changes, result.audit.taxonomy_version
    )
    assert [item.kind for item in profile.evidence] == ["education"]


@pytest.mark.parametrize("mutation", ["hash", "rubric", "support", "quote", "coverage"])
def test_import_revalidates_integrity(mutation: str) -> None:
    result = mixed_result().model_dump(mode="json")
    if mutation == "hash":
        result["audit"]["source_sha256"]["resume"] = "wrong"
    elif mutation == "rubric":
        result["audit"]["rubric_sha256"] = "wrong"
    elif mutation == "support":
        result["supported_claim_ids"].append("unsupported")
    elif mutation == "quote":
        result["draft"]["claims"][0]["citations"][0]["quote"] = "Invented quote"
    else:
        result["support_review"]["checks"].pop()
    with pytest.raises(ValueError):
        validate_understanding(
            UnderstandingResult.model_validate(result), load_taxonomy().version
        )


def test_claim_coverage_taxonomy_and_repeat_removal() -> None:
    result = mixed_result()
    changes = initial_claim_corrections(result)
    for invalid in [changes[:-1], [*changes, changes[0]]]:
        with pytest.raises(ValueError, match="every interpreted claim"):
            confirm_understanding(
                empty_profile(), result, invalid, result.audit.taxonomy_version
            )
    with pytest.raises(ValueError, match="Taxonomy changed"):
        validate_understanding(result, "stale")
    profile = confirm_understanding(
        empty_profile(), result, changes, result.audit.taxonomy_version
    )
    changes[0] = changes[0].model_copy(update={"decision": ClaimDecision.EXCLUDE})
    updated = confirm_understanding(
        profile, result, changes, result.audit.taxonomy_version
    )
    assert len(updated.evidence) == 1


def test_scoring_exclusion_survives_mapped_kind_labels_and_absence() -> None:
    result = mixed_result()
    taxonomy = load_taxonomy()
    profile = confirm_understanding(
        empty_profile(), result, initial_claim_corrections(result), taxonomy.version
    )
    baseline = resolve_competencies(empty_profile(), taxonomy, as_of=date(2026, 9, 11))
    rule = taxonomy.evidence_rules[0]
    for state in EvidenceState:
        forged = profile.evidence[0].model_copy(
            update={
                "kind": rule.evidence_kind,
                "quality": "top_venue",
                "state": state,
            }
        )
        altered = profile.model_copy(update={"evidence": [forged]})
        assert (
            resolve_competencies(altered, taxonomy, as_of=date(2026, 9, 11)) == baseline
        )
        with pytest.raises(EvidenceValueError, match="approved scoring mapping"):
            evaluate_evidence(
                forged,
                rule,
                load_evidence_configuration(taxonomy.evidence_configuration),
                as_of=date(2026, 9, 11),
            )


def test_standard_editor_cannot_change_imported_evidence() -> None:
    result = mixed_result()
    taxonomy = load_taxonomy()
    profile = confirm_understanding(
        empty_profile(), result, initial_claim_corrections(result), taxonomy.version
    )
    changes = [
        EvidenceCorrection.model_validate(
            {
                "evidence_id": item.id,
                **item.model_dump(
                    include={"raw_text", "kind", "state", "quality", "depth", "recency"}
                ),
            }
        )
        for item in profile.evidence
    ]
    changes[0] = changes[0].model_copy(update={"kind": "publication"})
    with pytest.raises(ValueError, match="interpretation review"):
        confirm_evidence(
            ConfirmationRequest(
                profile=profile,
                taxonomy_version=taxonomy.version,
                corrections=changes,
                confirmed=True,
            ),
            taxonomy,
        )
