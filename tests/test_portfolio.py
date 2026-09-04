"""Tests for constraint-respecting, balanced portfolio construction."""

from __future__ import annotations

import warnings
from decimal import Decimal

from unihive.models import Confidence, ReadinessBand
from unihive.portfolio import (
    CareerAlignment,
    LoadedPortfolioConfiguration,
    PortfolioCategory,
    PortfolioIssueCode,
    ProvisionalPortfolioWarning,
    ScoredProgramCandidate,
    StudentPortfolioConstraints,
    build_portfolio,
    load_portfolio_configuration,
)


def _configuration() -> LoadedPortfolioConfiguration:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalPortfolioWarning)
        return load_portfolio_configuration()


CONFIGURATION = _configuration()


def candidate(
    program_id: str,
    category: PortfolioCategory,
    *,
    annual_cost: str = "30000",
    funding_available: bool | None = True,
    location: str | None = "California",
    career_alignment: CareerAlignment = CareerAlignment.HIGH,
    data_confidence: Confidence = Confidence.HIGH,
) -> ScoredProgramCandidate:
    """Build a categorical scored-program fixture."""
    return ScoredProgramCandidate(
        program_id=program_id,
        program_name=f"Program {program_id}",
        category=category,
        readiness_band=ReadinessBand.COMPETITIVE,
        annual_cost=Decimal(annual_cost),
        funding_available=funding_available,
        location=location,
        career_alignment=career_alignment,
        data_confidence=data_confidence,
    )


def candidates_by_category(
    safe: int,
    target: int,
    ambitious: int,
) -> list[ScoredProgramCandidate]:
    """Build an ordered candidate pool with the requested category counts."""
    return [
        *(
            candidate(f"safe-{index}", PortfolioCategory.SAFE)
            for index in range(safe)
        ),
        *(
            candidate(f"target-{index}", PortfolioCategory.TARGET)
            for index in range(target)
        ),
        *(
            candidate(f"ambitious-{index}", PortfolioCategory.AMBITIOUS)
            for index in range(ambitious)
        ),
    ]


def test_entirely_ambitious_pool_reports_unmet_balance() -> None:
    result = build_portfolio(
        candidates_by_category(0, 0, 14),
        StudentPortfolioConstraints(),
        configuration=CONFIGURATION,
    )

    assert result.programs
    assert all(
        program.category is PortfolioCategory.AMBITIOUS
        for program in result.programs
    )
    assert result.unmet_constraints
    missing_categories = {
        issue.category
        for issue in result.unmet_constraints
        if issue.code is PortfolioIssueCode.CATEGORY_MINIMUM_NOT_MET
    }
    assert missing_categories == {
        PortfolioCategory.SAFE,
        PortfolioCategory.TARGET,
    }


def test_budget_filter_is_respected() -> None:
    pool = candidates_by_category(4, 5, 4)
    pool.append(
        candidate("over-budget-safe", PortfolioCategory.SAFE, annual_cost="75000")
    )
    result = build_portfolio(
        pool,
        StudentPortfolioConstraints(maximum_annual_cost=Decimal("50000")),
        configuration=CONFIGURATION,
    )

    assert result.programs
    assert all(
        program.annual_cost is not None
        and program.annual_cost <= Decimal("50000")
        for program in result.programs
    )
    assert "over-budget-safe" not in {
        program.program_id for program in result.programs
    }


def test_output_size_stays_in_configured_range() -> None:
    result = build_portfolio(
        candidates_by_category(6, 6, 6),
        StudentPortfolioConstraints(),
        configuration=CONFIGURATION,
    )

    size = len(result.programs)
    assert CONFIGURATION.values.minimum_size <= size
    assert size <= CONFIGURATION.values.maximum_size
    assert result.unmet_constraints == []


def test_all_student_constraints_are_respected() -> None:
    eligible = candidates_by_category(4, 5, 4)
    excluded = [
        candidate(
            "no-funding",
            PortfolioCategory.SAFE,
            funding_available=False,
        ),
        candidate(
            "wrong-location",
            PortfolioCategory.TARGET,
            location="New York",
        ),
        candidate(
            "low-alignment",
            PortfolioCategory.TARGET,
            career_alignment=CareerAlignment.LOW,
        ),
        candidate(
            "low-confidence",
            PortfolioCategory.AMBITIOUS,
            data_confidence=Confidence.LOW,
        ),
    ]
    result = build_portfolio(
        eligible + excluded,
        StudentPortfolioConstraints(
            funding_required=True,
            allowed_locations=("california",),
            minimum_career_alignment=CareerAlignment.MEDIUM,
            minimum_data_confidence=Confidence.MEDIUM,
        ),
        configuration=CONFIGURATION,
    )

    selected_ids = {program.program_id for program in result.programs}
    assert selected_ids.isdisjoint(
        {"no-funding", "wrong-location", "low-alignment", "low-confidence"}
    )


def test_too_few_feasible_candidates_reports_size_shortfall() -> None:
    result = build_portfolio(
        candidates_by_category(1, 1, 1),
        StudentPortfolioConstraints(),
        configuration=CONFIGURATION,
    )

    assert any(
        issue.code is PortfolioIssueCode.MINIMUM_PORTFOLIO_SIZE_NOT_MET
        for issue in result.unmet_constraints
    )
