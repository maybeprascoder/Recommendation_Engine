"""Core data contracts for the UniHive engine."""

from datetime import date, datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue

StructuredRecord = dict[str, JsonValue]


class CoreModel(BaseModel):
    """Base configuration shared by immutable engine data contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceState(StrEnum):
    """Verification or assessment state for a piece of evidence."""

    VERIFIED_PRESENT = "VERIFIED_PRESENT"
    SELF_REPORTED_PRESENT = "SELF_REPORTED_PRESENT"
    CONFIRMED_ABSENT = "CONFIRMED_ABSENT"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReadinessBand(StrEnum):
    """Categorical readiness output; never an admission probability."""

    EMERGING = "EMERGING"
    DEVELOPING = "DEVELOPING"
    COMPETITIVE = "COMPETITIVE"
    STRONG = "STRONG"


class Confidence(StrEnum):
    """Categorical confidence in an engine readout."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EligibilityStatus(StrEnum):
    """Deterministic program-eligibility result."""

    ELIGIBLE = "ELIGIBLE"
    CONDITIONALLY_ELIGIBLE = "CONDITIONALLY_ELIGIBLE"
    NOT_CURRENTLY_ELIGIBLE = "NOT_CURRENTLY_ELIGIBLE"
    UNKNOWN = "UNKNOWN"
    ELIGIBILITY_UNKNOWN = "UNKNOWN"


class EligibilityRuleType(StrEnum):
    """Supported deterministic eligibility rule kinds."""

    REQUIRED_PRIOR_DEGREE = "REQUIRED_PRIOR_DEGREE"
    MINIMUM_GPA = "MINIMUM_GPA"
    MANDATORY_COURSEWORK = "MANDATORY_COURSEWORK"
    ENGLISH_SCORE = "ENGLISH_SCORE"
    GRE_REQUIREMENT = "GRE_REQUIREMENT"
    WORK_EXPERIENCE = "WORK_EXPERIENCE"
    CITIZENSHIP_RESIDENCY = "CITIZENSHIP_RESIDENCY"
    DEADLINE = "DEADLINE"
    INTAKE_AVAILABILITY = "INTAKE_AVAILABILITY"


class EligibilityRuleOutcome(StrEnum):
    """Result of evaluating one eligibility rule."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EligibilityFailureEffect(StrEnum):
    """Overall status produced by a known failure of a configured rule."""

    CONDITIONALLY_ELIGIBLE = "CONDITIONALLY_ELIGIBLE"
    NOT_CURRENTLY_ELIGIBLE = "NOT_CURRENTLY_ELIGIBLE"


class ProfileShapeRuleType(StrEnum):
    """Supported explainable profile-shape adjustments."""

    HARD_PREREQUISITE_FLOOR = "HARD_PREREQUISITE_FLOOR"
    COHERENCE = "COHERENCE"


class ScoreExclusionReason(StrEnum):
    """Why a demanded competency was excluded from readiness arithmetic."""

    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CompetencyLevel(IntEnum):
    """Ordinal competency scale from initial exposure through expert practice.

    Unknownness is not a level: it is represented by ``EvidenceState.UNKNOWN``.
    The ordering is INTRODUCTORY < DEVELOPING < PROFICIENT < ADVANCED < EXPERT.
    """

    INTRODUCTORY = 1
    DEVELOPING = 2
    PROFICIENT = 3
    ADVANCED = 4
    EXPERT = 5


class Evidence(CoreModel):
    """A single state-tagged item extracted from a student source."""

    id: str
    kind: str
    raw_text: str
    state: EvidenceState
    quality: str | None
    depth: str | None
    recency: date | None
    source: str | None
    extraction_confidence: Confidence
    # Generic interpretation is evidence, but has no human-approved score mapping.
    scoring_exclusion: Literal["awaiting_approved_mapping"] | None = None


class EvidenceContribution(CoreModel):
    """An auditable trace of one item's competency contribution."""

    evidence_id: str
    rule_id: str
    state: EvidenceState
    quality: Decimal | None
    relevance: Decimal | None
    depth: Decimal | None
    verification: Decimal | None
    recency: Decimal | None
    combination_multiplier: Decimal | None
    contribution: Decimal | None


class StudentCompetency(CoreModel):
    """A competency level resolved from explicitly identified evidence."""

    competency_id: str
    level: CompetencyLevel | None
    state: EvidenceState
    contributing_evidence_ids: list[str]
    explanation_trace: list[EvidenceContribution]


class StudentProfile(CoreModel):
    """The structured student profile described in Build Spec section 5.1."""

    academic_history: list[StructuredRecord]
    normalized_gpa: Decimal | None
    courses: list[StructuredRecord]
    skills: list[str]
    projects: list[StructuredRecord]
    research: list[StructuredRecord]
    work: list[StructuredRecord]
    goals: list[str]
    constraints: list[str]
    tests: list[StructuredRecord]
    evidence: list[Evidence]
    citizenship: str | None = None
    residency: str | None = None


class CompetencyDemand(CoreModel):
    """A program's required level and configured weight for one competency."""

    required_level: CompetencyLevel
    weight: Decimal


class EligibilityRuleBase(CoreModel):
    """Fields shared by every sourced program eligibility rule."""

    id: str
    type: EligibilityRuleType
    source_url: HttpUrl
    failure_effect: EligibilityFailureEffect


class RequiredPriorDegreeRule(EligibilityRuleBase):
    """Accepted completed prior-degree values."""

    type: Literal[EligibilityRuleType.REQUIRED_PRIOR_DEGREE]
    accepted_degrees: list[str]


class MinimumGPARule(EligibilityRuleBase):
    """Minimum normalized GPA requirement."""

    type: Literal[EligibilityRuleType.MINIMUM_GPA]
    minimum_gpa: Decimal


class MandatoryCourseworkRule(EligibilityRuleBase):
    """Course identifiers that must be explicitly completed."""

    type: Literal[EligibilityRuleType.MANDATORY_COURSEWORK]
    required_courses: list[str]


class EnglishScoreRule(EligibilityRuleBase):
    """Accepted English tests and their configured minimum scores."""

    type: Literal[EligibilityRuleType.ENGLISH_SCORE]
    minimum_scores: dict[str, Decimal]


class GRERequirementRule(EligibilityRuleBase):
    """GRE presence or minimum-score requirement."""

    type: Literal[EligibilityRuleType.GRE_REQUIREMENT]
    required: bool
    minimum_score: Decimal | None


class WorkExperienceRule(EligibilityRuleBase):
    """Minimum explicitly reported work-experience duration."""

    type: Literal[EligibilityRuleType.WORK_EXPERIENCE]
    minimum_months: int


class CitizenshipResidencyRule(EligibilityRuleBase):
    """Accepted citizenship or residency values."""

    type: Literal[EligibilityRuleType.CITIZENSHIP_RESIDENCY]
    accepted_citizenships: list[str]
    accepted_residencies: list[str]


class DeadlineRule(EligibilityRuleBase):
    """Application deadline checked against an explicit evaluation date."""

    type: Literal[EligibilityRuleType.DEADLINE]
    deadline: date


class IntakeAvailabilityRule(EligibilityRuleBase):
    """Sourced availability state for one named intake."""

    type: Literal[EligibilityRuleType.INTAKE_AVAILABILITY]
    intake: str
    available: bool | None


EligibilityRule = Annotated[
    RequiredPriorDegreeRule
    | MinimumGPARule
    | MandatoryCourseworkRule
    | EnglishScoreRule
    | GRERequirementRule
    | WorkExperienceRule
    | CitizenshipResidencyRule
    | DeadlineRule
    | IntakeAvailabilityRule,
    Field(discriminator="type"),
]


class ProfileShapeRuleBase(CoreModel):
    """Shared sourced fields for a named profile-shape rule."""

    id: str
    type: ProfileShapeRuleType
    rationale: str
    source_url: HttpUrl


class HardPrerequisiteFloorRule(ProfileShapeRuleBase):
    """Cap the readiness band when a known hard prerequisite is unmet."""

    type: Literal[ProfileShapeRuleType.HARD_PREREQUISITE_FLOOR]
    competency_id: str
    minimum_level: CompetencyLevel
    maximum_band: ReadinessBand


class CoherenceRule(ProfileShapeRuleBase):
    """Configured adjustment for a demonstrated coherent competency shape."""

    type: Literal[ProfileShapeRuleType.COHERENCE]
    competency_ids: list[str]
    minimum_level: CompetencyLevel
    minimum_count: int
    adjustment: Decimal


ProfileShapeRule = Annotated[
    HardPrerequisiteFloorRule | CoherenceRule,
    Field(discriminator="type"),
]


class ProgramConfig(CoreModel):
    """A versioned and sourced program scoring configuration."""

    program_id: str
    university: str
    degree: str
    demand_profile: dict[str, CompetencyDemand]
    eligibility_rules: list[EligibilityRule]
    dimension_emphasis: dict[str, Decimal]
    version: str
    source_url: HttpUrl
    verified_on: date
    provisional: bool
    validated_by: str | None
    profile_shape_rules: list[ProfileShapeRule] = Field(default_factory=list)


class EligibilityRuleResult(CoreModel):
    """Auditable result for one sourced eligibility rule."""

    rule_id: str
    rule_type: EligibilityRuleType
    outcome: EligibilityRuleOutcome
    source_url: HttpUrl
    needed_information: list[str]


class EligibilityResult(CoreModel):
    """Separate deterministic eligibility readout and per-rule trace."""

    status: EligibilityStatus
    rule_breakdown: list[EligibilityRuleResult]
    needed_information: list[str]


class CompetencyScoreTrace(CoreModel):
    """One demanded competency's auditable readiness contribution."""

    competency_id: str
    state: EvidenceState
    demonstrated_level: CompetencyLevel | None
    expected_level: CompetencyLevel
    demand_weight: Decimal
    match_value: Decimal | None
    contribution: Decimal | None
    evidence_ids: list[str]
    evidence_trace: list[EvidenceContribution]
    exclusion_reason: ScoreExclusionReason | None


class ProfileShapeTrace(CoreModel):
    """Named explanation for one configured profile-shape rule."""

    rule_id: str
    rule_type: ProfileShapeRuleType
    applied: bool
    rationale: str
    adjustment: Decimal | None
    band_cap: ReadinessBand | None


class ProgramAlignment(CoreModel):
    """Continuous readiness comparison and its complete explanation trace."""

    readiness_value: Decimal | None
    base_readiness_value: Decimal | None
    contribution_sum: Decimal
    known_demand_weight: Decimal
    configured_demand_weight: Decimal
    competency_trace: list[CompetencyScoreTrace]
    profile_shape_trace: list[ProfileShapeTrace]
    band_config_version: str


class AuditRecord(CoreModel):
    """The provenance required to reproduce an assessment."""

    engine_version: str
    taxonomy_version: str
    program_config_version: str
    evidence_ids_used: list[str]
    missing_fields: list[str]
    source_urls: list[HttpUrl]
    timestamp: datetime
    confidence: Confidence
    scoring_config_version: str | None = None
    as_of: date | None = None
    profile_snapshot: StudentProfile | None = None
    program_config_snapshot: ProgramConfig | None = None
    preference_fit_snapshot: JsonValue = None
    admissions_outlook_snapshot: JsonValue = None


class Assessment(CoreModel):
    """The six distinct engine readouts and their reproducibility record."""

    pathway_readiness: ReadinessBand | None
    program_alignment: ProgramAlignment
    eligibility: EligibilityStatus
    preference_fit: JsonValue
    admissions_outlook: JsonValue
    data_confidence: Confidence
    audit: AuditRecord
    not_assessed: list[str]
