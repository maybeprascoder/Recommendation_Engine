"""Assessment audit enrichment and byte-identical replay."""

from __future__ import annotations

import warnings
from datetime import date, datetime

from pydantic import JsonValue

from unihive.competency import resolve_competencies
from unihive.eligibility import evaluate_eligibility
from unihive.models import Assessment, AuditRecord, ProgramConfig, StudentProfile
from unihive.scoring import (
    LoadedScoringConfiguration,
    ProvisionalScoringWarning,
    load_scoring_configuration,
    score,
)
from unihive.taxonomy import (
    ProvisionalTaxonomyWarning,
    Taxonomy,
    load_taxonomy,
)


class AuditError(ValueError):
    """Base error for incomplete or inconsistent replay information."""


class AuditVersionError(AuditError):
    """Raised when current deterministic data differs from the audit."""


class AuditReplayMismatch(AuditError):
    """Raised when replay does not serialize identically to the past result."""


def create_audited_assessment(
    profile: StudentProfile,
    program: ProgramConfig,
    *,
    taxonomy: Taxonomy,
    scoring_configuration: LoadedScoringConfiguration,
    as_of: date,
    timestamp: datetime,
    engine_version: str,
    preference_fit: JsonValue = None,
    admissions_outlook: JsonValue = None,
) -> Assessment:
    """Run the complete deterministic path and attach replayable inputs."""
    competencies = resolve_competencies(profile, taxonomy, as_of=as_of)
    eligibility = evaluate_eligibility(profile, program, as_of=as_of)
    assessment = score(
        competencies,
        program,
        taxonomy_version=taxonomy.version,
        engine_version=engine_version,
        timestamp=timestamp,
        eligibility=eligibility.status,
        preference_fit=preference_fit,
        admissions_outlook=admissions_outlook,
        configuration=scoring_configuration,
    )
    return attach_replay_context(assessment, profile, program, as_of=as_of)


def attach_replay_context(
    assessment: Assessment,
    profile: StudentProfile,
    program: ProgramConfig,
    *,
    as_of: date,
) -> Assessment:
    """Attach the immutable inputs required to replay one assessment."""
    if assessment.audit.program_config_version != program.version:
        raise AuditVersionError("program snapshot version differs from assessment")

    audit = assessment.audit.model_copy(
        update={
            "as_of": as_of,
            "profile_snapshot": profile,
            "program_config_snapshot": program,
            "preference_fit_snapshot": assessment.preference_fit,
            "admissions_outlook_snapshot": assessment.admissions_outlook,
        }
    )
    return assessment.model_copy(update={"audit": audit})


def replay_assessment(
    expected: Assessment,
    *,
    taxonomy: Taxonomy | None = None,
    scoring_configuration: LoadedScoringConfiguration | None = None,
) -> Assessment:
    """Replay from the embedded audit and assert byte-identical output."""
    audit = expected.audit
    profile, program, as_of = _require_replay_context(audit)
    loaded_taxonomy = taxonomy or _load_taxonomy_for_replay()
    loaded_scoring = scoring_configuration or _load_scoring_for_replay()
    _validate_versions(expected, loaded_taxonomy, loaded_scoring)

    replayed = create_audited_assessment(
        profile,
        program,
        taxonomy=loaded_taxonomy,
        scoring_configuration=loaded_scoring,
        as_of=as_of,
        timestamp=audit.timestamp,
        engine_version=audit.engine_version,
        preference_fit=audit.preference_fit_snapshot,
        admissions_outlook=audit.admissions_outlook_snapshot,
    )
    if replayed.model_dump_json() != expected.model_dump_json():
        raise AuditReplayMismatch("replayed assessment is not byte-identical")
    return replayed


def _require_replay_context(
    audit: AuditRecord,
) -> tuple[StudentProfile, ProgramConfig, date]:
    if audit.profile_snapshot is None:
        raise AuditError("audit has no profile snapshot")
    if audit.program_config_snapshot is None:
        raise AuditError("audit has no program-config snapshot")
    if audit.as_of is None:
        raise AuditError("audit has no as_of date")
    return audit.profile_snapshot, audit.program_config_snapshot, audit.as_of


def _validate_versions(
    expected: Assessment,
    taxonomy: Taxonomy,
    scoring: LoadedScoringConfiguration,
) -> None:
    audit = expected.audit
    if audit.taxonomy_version != taxonomy.version:
        raise AuditVersionError("taxonomy version differs from audit")
    if audit.scoring_config_version != scoring.version:
        raise AuditVersionError("scoring configuration version differs from audit")
    if expected.program_alignment.band_config_version != scoring.version:
        raise AuditVersionError("assessment band configuration differs from audit")
    program = audit.program_config_snapshot
    if program is None or audit.program_config_version != program.version:
        raise AuditVersionError("program configuration version differs from audit")


def _load_taxonomy_for_replay() -> Taxonomy:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalTaxonomyWarning)
        return load_taxonomy()


def _load_scoring_for_replay() -> LoadedScoringConfiguration:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalScoringWarning)
        return load_scoring_configuration()
