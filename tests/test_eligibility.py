"""Tests for every deterministic eligibility rule and overall precedence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from unihive.eligibility import (
    ProvisionalProgramWarning,
    evaluate_eligibility,
    load_program_config,
)
from unihive.models import (
    CitizenshipResidencyRule,
    DeadlineRule,
    EligibilityFailureEffect,
    EligibilityRule,
    EligibilityRuleOutcome,
    EligibilityStatus,
    EnglishScoreRule,
    GRERequirementRule,
    IntakeAvailabilityRule,
    MandatoryCourseworkRule,
    MinimumGPARule,
    ProgramConfig,
    RequiredPriorDegreeRule,
    StructuredRecord,
    StudentProfile,
    WorkExperienceRule,
)

AS_OF = date(2026, 1, 15)
SOURCE_URL = "https://example.edu/program/requirements"
HARD = EligibilityFailureEffect.NOT_CURRENTLY_ELIGIBLE


def profile(
    *,
    academic_history: list[StructuredRecord] | None = None,
    normalized_gpa: Decimal | None = None,
    courses: list[StructuredRecord] | None = None,
    tests: list[StructuredRecord] | None = None,
    work: list[StructuredRecord] | None = None,
    citizenship: str | None = None,
    residency: str | None = None,
) -> StudentProfile:
    """Build a complete profile using only explicit eligibility inputs."""
    return StudentProfile(
        academic_history=academic_history or [],
        normalized_gpa=normalized_gpa,
        courses=courses or [],
        skills=[],
        projects=[],
        research=[],
        work=work or [],
        goals=[],
        constraints=[],
        tests=tests or [],
        evidence=[],
        citizenship=citizenship,
        residency=residency,
    )


def program(*rules: EligibilityRule) -> ProgramConfig:
    """Build a minimal sourced program configuration for rule tests."""
    return ProgramConfig(
        program_id="test-program",
        university="Example University",
        degree="MS",
        demand_profile={},
        eligibility_rules=list(rules),
        dimension_emphasis={},
        version="test-v1",
        source_url=SOURCE_URL,
        verified_on=AS_OF,
        provisional=True,
        validated_by=None,
    )


def outcome_for(
    student: StudentProfile, rule: EligibilityRule
) -> EligibilityRuleOutcome:
    """Evaluate one rule and return its per-rule outcome."""
    result = evaluate_eligibility(student, program(rule), as_of=AS_OF)
    assert str(result.rule_breakdown[0].source_url) == SOURCE_URL
    return result.rule_breakdown[0].outcome


def test_required_prior_degree_rule() -> None:
    rule = RequiredPriorDegreeRule(
        id="degree",
        type="REQUIRED_PRIOR_DEGREE",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        accepted_degrees=["BS", "BE"],
    )
    student = profile(
        academic_history=[{"degree": "BS", "completed": True}]
    )

    assert outcome_for(student, rule) is EligibilityRuleOutcome.PASS


def test_minimum_gpa_rule() -> None:
    rule = MinimumGPARule(
        id="gpa",
        type="MINIMUM_GPA",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        minimum_gpa=Decimal("3.0"),
    )

    assert outcome_for(profile(normalized_gpa=Decimal("2.9")), rule) is (
        EligibilityRuleOutcome.FAIL
    )


def test_mandatory_coursework_rule() -> None:
    rule = MandatoryCourseworkRule(
        id="courses",
        type="MANDATORY_COURSEWORK",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        required_courses=["Algorithms", "Operating Systems"],
    )
    student = profile(
        courses=[
            {"course_id": "Algorithms", "completed": True},
            {"name": "Operating Systems", "completed": True},
        ]
    )

    assert outcome_for(student, rule) is EligibilityRuleOutcome.PASS


def test_english_score_rule() -> None:
    rule = EnglishScoreRule(
        id="english",
        type="ENGLISH_SCORE",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        minimum_scores={"TOEFL": Decimal("100"), "IELTS": Decimal("7")},
    )

    assert outcome_for(
        profile(tests=[{"test": "TOEFL", "score": 105}]), rule
    ) is EligibilityRuleOutcome.PASS


def test_gre_requirement_rule() -> None:
    rule = GRERequirementRule(
        id="gre",
        type="GRE_REQUIREMENT",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        required=True,
        minimum_score=Decimal("320"),
    )

    assert outcome_for(
        profile(tests=[{"test": "GRE", "score": 321}]), rule
    ) is EligibilityRuleOutcome.PASS


def test_optional_gre_is_not_applicable() -> None:
    rule = GRERequirementRule(
        id="gre-optional",
        type="GRE_REQUIREMENT",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        required=False,
        minimum_score=None,
    )

    assert outcome_for(profile(), rule) is EligibilityRuleOutcome.NOT_APPLICABLE


def test_work_experience_rule() -> None:
    rule = WorkExperienceRule(
        id="work",
        type="WORK_EXPERIENCE",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        minimum_months=24,
    )

    assert outcome_for(profile(work=[{"months": 24}]), rule) is (
        EligibilityRuleOutcome.PASS
    )


def test_citizenship_residency_rule() -> None:
    rule = CitizenshipResidencyRule(
        id="residency",
        type="CITIZENSHIP_RESIDENCY",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        accepted_citizenships=["US"],
        accepted_residencies=["Permanent Resident"],
    )

    assert outcome_for(profile(residency="Permanent Resident"), rule) is (
        EligibilityRuleOutcome.PASS
    )


def test_deadline_rule() -> None:
    rule = DeadlineRule(
        id="deadline",
        type="DEADLINE",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        deadline=date(2026, 1, 1),
    )

    assert outcome_for(profile(), rule) is EligibilityRuleOutcome.FAIL


def test_intake_availability_rule() -> None:
    rule = IntakeAvailabilityRule(
        id="intake",
        type="INTAKE_AVAILABILITY",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        intake="Fall 2026",
        available=True,
    )

    assert outcome_for(profile(), rule) is EligibilityRuleOutcome.PASS


def test_unknown_rule_blocks_clean_eligible() -> None:
    passing_rule = MinimumGPARule(
        id="gpa",
        type="MINIMUM_GPA",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        minimum_gpa=Decimal("3.0"),
    )
    unknown_rule = EnglishScoreRule(
        id="english",
        type="ENGLISH_SCORE",
        source_url=SOURCE_URL,
        failure_effect=HARD,
        minimum_scores={"TOEFL": Decimal("100")},
    )

    result = evaluate_eligibility(
        profile(normalized_gpa=Decimal("3.5")),
        program(passing_rule, unknown_rule),
        as_of=AS_OF,
    )

    assert result.status is EligibilityStatus.ELIGIBILITY_UNKNOWN
    assert result.rule_breakdown[1].outcome is EligibilityRuleOutcome.UNKNOWN
    assert result.needed_information == ["tests.toefl.score"]


@pytest.mark.parametrize(
    "rule",
    [
        RequiredPriorDegreeRule(
            id="degree-missing",
            type="REQUIRED_PRIOR_DEGREE",
            source_url=SOURCE_URL,
            failure_effect=HARD,
            accepted_degrees=["BS"],
        ),
        MinimumGPARule(
            id="gpa-missing",
            type="MINIMUM_GPA",
            source_url=SOURCE_URL,
            failure_effect=HARD,
            minimum_gpa=Decimal("3.0"),
        ),
        MandatoryCourseworkRule(
            id="course-missing",
            type="MANDATORY_COURSEWORK",
            source_url=SOURCE_URL,
            failure_effect=HARD,
            required_courses=["Algorithms"],
        ),
        EnglishScoreRule(
            id="english-missing",
            type="ENGLISH_SCORE",
            source_url=SOURCE_URL,
            failure_effect=HARD,
            minimum_scores={"TOEFL": Decimal("100")},
        ),
        GRERequirementRule(
            id="gre-missing",
            type="GRE_REQUIREMENT",
            source_url=SOURCE_URL,
            failure_effect=HARD,
            required=True,
            minimum_score=None,
        ),
        WorkExperienceRule(
            id="work-missing",
            type="WORK_EXPERIENCE",
            source_url=SOURCE_URL,
            failure_effect=HARD,
            minimum_months=12,
        ),
        CitizenshipResidencyRule(
            id="residency-missing",
            type="CITIZENSHIP_RESIDENCY",
            source_url=SOURCE_URL,
            failure_effect=HARD,
            accepted_citizenships=["US"],
            accepted_residencies=[],
        ),
        IntakeAvailabilityRule(
            id="intake-missing",
            type="INTAKE_AVAILABILITY",
            source_url=SOURCE_URL,
            failure_effect=HARD,
            intake="Fall 2026",
            available=None,
        ),
    ],
)
def test_missing_input_is_unknown(rule: EligibilityRule) -> None:
    result = evaluate_eligibility(profile(), program(rule), as_of=AS_OF)

    assert result.rule_breakdown[0].outcome is EligibilityRuleOutcome.UNKNOWN
    assert result.status is EligibilityStatus.ELIGIBILITY_UNKNOWN
    assert result.needed_information


def test_configured_conditional_failure() -> None:
    rule = MinimumGPARule(
        id="conditional-gpa",
        type="MINIMUM_GPA",
        source_url=SOURCE_URL,
        failure_effect=EligibilityFailureEffect.CONDITIONALLY_ELIGIBLE,
        minimum_gpa=Decimal("3.0"),
    )

    result = evaluate_eligibility(
        profile(normalized_gpa=Decimal("2.9")), program(rule), as_of=AS_OF
    )

    assert result.rule_breakdown[0].outcome is EligibilityRuleOutcome.FAIL
    assert result.status is EligibilityStatus.CONDITIONALLY_ELIGIBLE


def test_program_yaml_loads_typed_rules(tmp_path: Path) -> None:
    program_path = tmp_path / "example.yaml"
    program_path.write_text(
        """program_id: example-ms
university: Example University
degree: MS
demand_profile: {}
eligibility_rules:
  - id: gpa
    type: MINIMUM_GPA
    source_url: https://example.edu/program/requirements
    failure_effect: NOT_CURRENTLY_ELIGIBLE
    minimum_gpa: 3.0
dimension_emphasis: {}
version: v1
source_url: https://example.edu/program
verified_on: "2026-01-01"
provisional: true
validated_by: null
""",
        encoding="utf-8",
    )

    with pytest.warns(ProvisionalProgramWarning):
        loaded = load_program_config(program_path)

    rule = loaded.eligibility_rules[0]
    assert isinstance(rule, MinimumGPARule)
    assert rule.minimum_gpa == Decimal("3.0")
