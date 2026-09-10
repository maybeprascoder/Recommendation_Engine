"""Deterministic report response over a replayable assessment.

Implements Experience section 3 without changing the six core readouts or
inventing alternative programs or action candidates when none are supplied.
"""

from enum import StrEnum
from typing import Literal

from unihive.alternatives import ChosenPath, evaluate_alternative_pathways
from unihive.audit import AuditError, AuditVersionError
from unihive.eligibility import evaluate_eligibility
from unihive.models import Assessment, CoreModel, EligibilityResult
from unihive.report import ReportStructure, ReportUnknown, assemble_report
from unihive.scoring import LoadedScoringConfiguration
from unihive.taxonomy import Taxonomy


class LimitationCode(StrEnum):
    """Unavailable inputs for the single-program report flow."""

    ALTERNATIVES_NOT_ASSESSED = "ALTERNATIVES_NOT_ASSESSED"
    ACTIONS_NOT_ASSESSED = "ACTIONS_NOT_ASSESSED"


class ReportLimitation(CoreModel):
    code: LimitationCode
    message: str


class ScoringResponse(CoreModel):
    """Versioned API envelope; Assessment and its audit stay unchanged."""

    response_version: Literal["report-v1"] = "report-v1"
    assessment: Assessment
    eligibility_result: EligibilityResult
    report: ReportStructure
    provisional: bool
    limitations: list[ReportLimitation]


def build_scoring_response(
    assessment: Assessment,
    *,
    taxonomy: Taxonomy,
    scoring_configuration: LoadedScoringConfiguration,
) -> ScoringResponse:
    """Assemble all six report sections from the assessment's exact inputs."""
    audit = assessment.audit
    profile = audit.profile_snapshot
    program = audit.program_config_snapshot
    if profile is None or program is None or audit.as_of is None:
        raise AuditError("report requires complete assessment replay inputs")
    if (
        audit.taxonomy_version != taxonomy.version
        or audit.program_config_version != program.version
        or audit.scoring_config_version != scoring_configuration.version
    ):
        raise AuditVersionError("report configuration differs from assessment")
    eligibility = evaluate_eligibility(profile, program, as_of=audit.as_of)
    if eligibility.status is not assessment.eligibility:
        raise AuditError("eligibility breakdown differs from assessment status")
    pathways = evaluate_alternative_pathways(
        ChosenPath(
            path_id=program.program_id,
            field=program.degree,
            readiness_band=assessment.pathway_readiness,
        ),
        [],
    )
    report = assemble_report(
        profile,
        assessment,
        pathways,
        [],
        taxonomy=taxonomy,
        program=program,
        as_of=audit.as_of,
        scoring_configuration=scoring_configuration,
    )
    # Unknown eligibility inputs also belong in the report, without becoming
    # competency gaps or altering the historical assessment/audit contract.
    known_unknowns = {item.field for item in report.what_we_cannot_assess_yet}
    eligibility_unknowns = [
        ReportUnknown(
            field=field,
            demand_weight=None,
            needed_to_resolve=f"Provide {field} to evaluate eligibility.",
        )
        for field in eligibility.needed_information
        if field not in known_unknowns
    ]
    report = report.model_copy(
        update={
            "what_we_cannot_assess_yet": [
                *report.what_we_cannot_assess_yet,
                *eligibility_unknowns,
            ],
        }
    )
    provisional = (
        program.provisional
        or scoring_configuration.values.provisional
        or any(node.provisional for node in taxonomy.competencies)
        or any(rule.provisional for rule in taxonomy.evidence_rules)
        or taxonomy.evidence_configuration.get("provisional") is True
    )
    return ScoringResponse(
        assessment=assessment,
        eligibility_result=eligibility,
        report=report,
        provisional=provisional,
        limitations=[
            ReportLimitation(
                code=LimitationCode.ALTERNATIVES_NOT_ASSESSED,
                message="Alternatives not assessed: no comparison programs supplied.",
            ),
            ReportLimitation(
                code=LimitationCode.ACTIONS_NOT_ASSESSED,
                message="Actions not assessed: no reviewed action candidates supplied.",
            ),
        ],
    )
