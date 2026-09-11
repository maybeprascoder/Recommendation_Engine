"""Narrow behavioral checks for synthetic cases, separate from expert review."""

from __future__ import annotations

from unihive.understanding import UnderstandingResult


def check_behavior(case_id: str, result: UnderstandingResult) -> list[str] | None:
    """Return failed checks, or None when this case has no automated oracle.

    These checks enforce specific expectations on known synthetic examples.
    They do not evaluate every semantic statement or certify admissions quality.
    """
    claims = [
        item for item in result.draft.claims if item.id in result.supported_claim_ids
    ]
    judgments = [
        item
        for item in result.draft.judgments
        if item.id in result.supported_judgment_ids
    ]
    skills = [
        item
        for item in result.draft.competencies
        if item.id in result.supported_competency_ids
    ]
    failures: list[str] = []
    if case_id == "keyword-list":
        if judgments or skills:
            failures.append("A skill list must not establish assessed competencies")
        if not result.questions:
            failures.append("A skill-only profile should request supporting evidence")
    elif case_id == "duplicate-work":
        if len(claims) != 1:
            failures.append("Repeated descriptions must resolve to one canonical work")
    elif case_id == "team-ownership":
        credited_ids = {item.claim_id for item in [*judgments, *skills]}
        for claim in claims:
            if claim.id in credited_ids and "teammates" in claim.statement.lower():
                failures.append(
                    "The student's evidence must not credit teammates' work"
                )
        if not any("slides" in claim.statement.lower() for claim in claims):
            failures.append("The student's own slide contribution must remain visible")
    elif case_id == "school-leaver":
        if not any("debate" in claim.statement.lower() for claim in claims):
            failures.append("The debate-club activity must remain visible")
        if not result.draft.academics:
            failures.append(
                "School status needs an academic record, with unknowns allowed"
            )
        for judgment in judgments:
            claim = next(item for item in claims if item.id == judgment.claim_id)
            if "no publications" in claim.statement.lower():
                failures.append(
                    "An absence of publications must not become an achievement"
                )
    elif case_id == "missing-scale":
        records = result.draft.academics
        if not any(
            record.grade == "3.5" and record.grade_scale is None for record in records
        ):
            failures.append("GPA 3.5 must retain an unknown grading scale")
    elif case_id == "unfamiliar-venue":
        if any(item.label == "externally_reviewed" for item in judgments):
            failures.append("Venue name alone cannot establish external review")
    else:
        return None
    return failures
