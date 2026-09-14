"""Generic confirmation preserves provenance and cannot confer scoring credit."""

import json
from datetime import date
from pathlib import Path

import pytest
from understanding_samples import mixed_result, qualitative_result

from unihive.competency import resolve_competencies
from unihive.evidence import (
    EvidenceValueError,
    evaluate_evidence,
    load_evidence_configuration,
)
from unihive.models import EvidenceState, StudentProfile
from unihive.review import ConfirmationRequest, EvidenceCorrection, confirm_evidence
from unihive.taxonomy import (
    JudgmentRequirement,
    QualitativeEvidenceMapping,
    load_taxonomy,
)
from unihive.understanding import UnderstandingResult
from unihive.understanding_review import (
    AcademicCorrection,
    ClaimCorrection,
    ClaimDecision,
    JudgmentCorrection,
    confirm_understanding,
    initial_academic_corrections,
    initial_claim_corrections,
    initial_judgment_corrections,
    validate_understanding,
)


def empty_profile() -> StudentProfile:
    data = json.loads((Path(__file__).parent / "fixtures/cli/profile.json").read_text())
    data.update(evidence=[], academic_history=[], normalized_gpa=None)
    return StudentProfile.model_validate(data)


def confirm_result(
    profile: StudentProfile,
    result: UnderstandingResult,
    changes: list[ClaimCorrection] | None = None,
    academics: list[AcademicCorrection] | None = None,
    judgments: list[JudgmentCorrection] | None = None,
) -> StudentProfile:
    taxonomy = load_taxonomy()
    return confirm_understanding(
        profile,
        result,
        changes if changes is not None else initial_claim_corrections(result),
        academics if academics is not None else initial_academic_corrections(result),
        judgments if judgments is not None else initial_judgment_corrections(result),
        taxonomy,
    )


def test_canonical_student_claims_only_and_no_academic_conversion() -> None:
    result = mixed_result()
    changes = initial_claim_corrections(result)
    # Even explicitly confirming everything cannot promote rejected claims.
    changes = [
        change.model_copy(update={"decision": ClaimDecision.CONFIRM})
        for change in changes
    ]
    profile = confirm_result(empty_profile(), result, changes)
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
    assert profile.normalized_gpa is None
    assert len(profile.academic_history) == 1
    academic = profile.academic_history[0]
    assert academic["institution"] == "Example College"
    assert academic["degree"] == "BSc"
    assert academic["grade"] == "8.2"
    assert academic["grade_scale"] == "10"
    assert "completed" not in academic
    assert academic["record_state"] == "source_supported"
    assert result.draft.academics[0].grade_scale == "10"
    assert confirm_result(profile, result, changes) == profile


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
    profile = confirm_result(empty_profile(), result, changes)
    assert [item.kind for item in profile.evidence] == ["education"]


def test_academic_correction_projects_original_scale_without_normalizing() -> None:
    result = mixed_result()
    academics = initial_academic_corrections(result)
    academics[0] = academics[0].model_copy(
        update={
            "grade": "8.4",
            "notes": "Student corrected the transcribed grade.",
        }
    )
    profile = confirm_result(empty_profile(), result, academics=academics)

    assert profile.normalized_gpa is None
    assert profile.academic_history[0]["grade"] == "8.4"
    assert profile.academic_history[0]["grade_scale"] == "10"
    assert profile.academic_history[0]["record_state"] == "student_corrected"
    academics[0] = academics[0].model_copy(update={"decision": ClaimDecision.EXCLUDE})
    assert confirm_result(profile, result, academics=academics).academic_history == []


def test_calibrated_mapping_still_requires_supported_unchanged_labels() -> None:
    result = qualitative_result(
        "I designed and evaluated a multilingual classifier.",
        labels={"depth": "designed"},
        skills={"classifier design": "machine_learning"},
    )
    taxonomy = load_taxonomy()
    rule = taxonomy.evidence_rules[-1].model_copy(
        update={
            "provisional": False,
            "validated_by": "Synthetic expert",
            "source": "Synthetic expert review record",
        }
    )
    mapping = QualitativeEvidenceMapping(
        id="designed_project_to_ml",
        claim_category="project",
        rubric_sha256=result.audit.rubric_sha256,
        judgment_requirements=(
            JudgmentRequirement(dimension="depth", labels=("designed",)),
        ),
        evidence_rule_id=rule.id,
        quality_label="substantive",
        depth_label="designed_or_investigated",
        validated_by="Synthetic expert",
        validated_on=date(2026, 9, 11),
        source="Synthetic expert review record",
    )
    approved = taxonomy.model_copy(
        update={"evidence_rules": (rule,), "qualitative_mappings": (mapping,)}
    )
    profile = confirm_understanding(
        empty_profile(),
        result,
        initial_claim_corrections(result),
        initial_academic_corrections(result),
        initial_judgment_corrections(result),
        approved,
    )

    mapped = [item for item in profile.evidence if item.approved_mapping_id]
    assert len(mapped) == 1
    assert mapped[0].approved_mapping_id == mapping.id
    assert mapped[0].scoring_exclusion is None
    competencies = resolve_competencies(profile, approved, as_of=date(2026, 9, 11))
    machine_learning = next(
        item for item in competencies if item.competency_id == "machine_learning"
    )
    assert mapped[0].id in machine_learning.contributing_evidence_ids

    judgment_changes = initial_judgment_corrections(result)
    index = next(
        index
        for index, change in enumerate(judgment_changes)
        if change.judgment_id == "depth"
    )
    judgment_changes[index] = judgment_changes[index].model_copy(
        update={"label": "applied", "notes": "Student corrected the label."}
    )
    corrected = confirm_understanding(
        empty_profile(),
        result,
        initial_claim_corrections(result),
        initial_academic_corrections(result),
        judgment_changes,
        approved,
    )
    assert not [item for item in corrected.evidence if item.approved_mapping_id]


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
            UnderstandingResult.model_validate(result),
            load_taxonomy().understanding_version,
        )


def test_claim_coverage_taxonomy_and_repeat_removal() -> None:
    result = mixed_result()
    changes = initial_claim_corrections(result)
    for invalid in [changes[:-1], [*changes, changes[0]]]:
        with pytest.raises(ValueError, match="every interpreted claim"):
            confirm_understanding(
                empty_profile(),
                result,
                invalid,
                initial_academic_corrections(result),
                initial_judgment_corrections(result),
                load_taxonomy(),
            )
    with pytest.raises(ValueError, match="Taxonomy changed"):
        validate_understanding(result, "stale")
    with pytest.raises(ValueError, match="every qualitative judgment"):
        confirm_understanding(
            empty_profile(),
            result,
            changes,
            initial_academic_corrections(result),
            initial_judgment_corrections(result)[:-1],
            load_taxonomy(),
        )
    profile = confirm_result(empty_profile(), result, changes)
    changes[0] = changes[0].model_copy(update={"decision": ClaimDecision.EXCLUDE})
    updated = confirm_result(profile, result, changes)
    assert len(updated.evidence) == 1


def test_scoring_exclusion_survives_mapped_kind_labels_and_absence() -> None:
    result = mixed_result()
    taxonomy = load_taxonomy()
    profile = confirm_understanding(
        empty_profile(),
        result,
        initial_claim_corrections(result),
        initial_academic_corrections(result),
        initial_judgment_corrections(result),
        taxonomy,
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
        empty_profile(),
        result,
        initial_claim_corrections(result),
        initial_academic_corrections(result),
        initial_judgment_corrections(result),
        taxonomy,
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
