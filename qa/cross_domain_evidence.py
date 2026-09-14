"""Cross-domain reference, adversarial and live evaluation of the existing pipeline.

Recorded results test contracts, never model accuracy. Live results use only the
explicitly configured provider. Training exports exclude arithmetic diagnostics.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from pydantic import Field, JsonValue

from unihive.competency import resolve_competencies
from unihive.llm.analysis_cli import RecordedClient, RecordedResponses
from unihive.llm.provider import (
    CompatibleChatClient,
    Completion,
    ProviderError,
    StructuredClient,
)
from unihive.llm.understanding import analyze_documents
from unihive.models import CoreModel, StudentProfile
from unihive.taxonomy import Taxonomy, load_taxonomy
from unihive.understanding import (
    ClaimAttribution,
    ClaimPresence,
    ContextKind,
    EvidenceCategory,
    SourceDocument,
    SupportReview,
    UnderstandingDraft,
    UnderstandingResult,
    load_evaluation_rubric,
    supported_context_ids,
    supported_ids,
    validate_draft,
)
from unihive.understanding_review import (
    confirm_understanding,
    initial_academic_corrections,
    initial_claim_corrections,
    initial_judgment_corrections,
)

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/understanding/cross_domain_golden.json"
)
AS_OF = date(2026, 9, 12)


class InstrumentedClient:
    """Record bounded call timing and sizes without retaining private source text."""

    def __init__(self, client: StructuredClient) -> None:
        self._client = client
        self.provider = client.provider
        self.model = client.model
        self.calls: list[dict[str, str | int | float]] = []

    def complete(
        self,
        *,
        instructions: str,
        payload: str,
        schema: dict[str, JsonValue],
        name: str,
    ) -> Completion:
        started = perf_counter()
        status = "completed"
        try:
            return self._client.complete(
                instructions=instructions,
                payload=payload,
                schema=schema,
                name=name,
            )
        except ProviderError:
            status = "provider_error"
            raise
        finally:
            self.calls.append(
                {
                    "name": name,
                    "status": status,
                    "seconds": round(perf_counter() - started, 2),
                    "instructions_chars": len(instructions),
                    "payload_chars": len(payload),
                    "schema_chars": len(json.dumps(schema)),
                }
            )


class SemanticContext(CoreModel):
    domain_concepts: list[str]
    recognized_tools: list[str]
    methods_performed: list[str]
    note: str


class SupportedIds(CoreModel):
    claims: list[str]
    judgments: list[str]
    competencies: list[str]
    contexts: list[str] = Field(default_factory=list)


class ExpectedContext(CoreModel):
    kind: ContextKind
    label: str
    exact_label: bool = True


class ClaimExpectation(CoreModel):
    """A provisional oracle anchored to a specific synthetic source passage."""

    source_quote: str = Field(min_length=1)
    attribution: ClaimAttribution = ClaimAttribution.STUDENT
    presence: ClaimPresence
    allowed_categories: list[EvidenceCategory] = Field(min_length=1)
    competency_ids: list[str] = Field(default_factory=list)
    optional_competency_ids: list[str] = Field(default_factory=list)
    one_of_competency_ids: list[str] = Field(default_factory=list)
    contexts: list[ExpectedContext] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    forbid_skills: bool = False
    require_uncatalogued_skill: bool = False
    require_clarification: bool = False
    uncertainty_terms: list[str] = Field(default_factory=list)


class ReviewChallenge(CoreModel):
    draft: UnderstandingDraft
    expected_review: SupportReview
    rejected_ids: list[str]


class GoldenCase(CoreModel):
    id: str
    domain: str
    strength: str
    source_text: str
    semantic_context: SemanticContext
    expected_understanding: UnderstandingDraft
    expected_support_review: SupportReview
    expected_supported_ids: SupportedIds
    unknown_fields: list[str]
    coverage_gaps: list[str]
    confirmed_absence: list[str]
    forbidden_inferences: list[str]
    forbidden_competency_ids: list[str]
    annotation_status: str
    validated_by: str | None
    review_challenge: ReviewChallenge
    claim_expectations: list[ClaimExpectation] = Field(default_factory=list)
    live_focus: bool = False


class GoldenSuite(CoreModel):
    version: str
    provisional: bool
    validated_by: str | None
    source: str | None
    description: str
    cases: list[GoldenCase]
    probes: list[GoldenCase] = Field(default_factory=list)


def load_suite(path: Path = FIXTURES) -> GoldenSuite:
    suite = GoldenSuite.model_validate_json(path.read_text("utf-8"))
    ids = [case.id for case in [*suite.cases, *suite.probes]]
    if len(ids) != len(set(ids)):
        raise ValueError("Golden fixture IDs must be unique")
    return suite


def documents(case: GoldenCase) -> list[SourceDocument]:
    return [SourceDocument(id="source", text=case.source_text)]


def validate_case(case: GoldenCase, taxonomy: Taxonomy) -> None:
    catalog = {node.id: node.description for node in taxonomy.competencies}
    for draft, review in [
        (case.expected_understanding, case.expected_support_review),
        (case.review_challenge.draft, case.review_challenge.expected_review),
    ]:
        validate_draft(draft, documents(case), load_evaluation_rubric(), catalog)
        supported_ids(draft, review)
    actual = supported_ids(case.expected_understanding, case.expected_support_review)
    expected = case.expected_supported_ids
    if actual != (expected.claims, expected.judgments, expected.competencies):
        raise ValueError(f"Incorrect supported-ID oracle: {case.id}")
    if (
        supported_context_ids(case.expected_understanding, case.expected_support_review)
        != expected.contexts
    ):
        raise ValueError(f"Incorrect context-ID oracle: {case.id}")
    anchors = [item.source_quote for item in case.claim_expectations]
    if len(set(anchors)) != len(anchors) or any(
        quote not in case.source_text for quote in anchors
    ):
        raise ValueError(
            f"Claim expectation anchors must be distinct source quotes: {case.id}"
        )
    if any(
        (
            set(item.competency_ids)
            | set(item.optional_competency_ids)
            | set(item.one_of_competency_ids)
        )
        - set(catalog)
        for item in case.claim_expectations
    ):
        raise ValueError(f"Claim expectation uses an unknown competency: {case.id}")
    unknowns = sorted(
        {
            j.dimension
            for j in case.expected_understanding.judgments
            if j.label == "unknown"
        }
    )
    if unknowns != sorted(case.unknown_fields):
        raise ValueError(f"Incorrect unknown-field oracle: {case.id}")


def interpret(
    case: GoldenCase,
    taxonomy: Taxonomy,
    *,
    challenge: bool = False,
    client: StructuredClient | None = None,
) -> UnderstandingResult:
    if client is None:
        client = RecordedClient(
            RecordedResponses(
                draft=case.review_challenge.draft
                if challenge
                else case.expected_understanding,
                review=case.review_challenge.expected_review
                if challenge
                else case.expected_support_review,
            )
        )
    return analyze_documents(
        documents(case),
        client,
        taxonomy_version=taxonomy.understanding_version,
        competency_catalog={
            node.id: node.description for node in taxonomy.competencies
        },
    )


def empty_profile() -> StudentProfile:
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
        evidence=[],
    )


def project(result: UnderstandingResult, taxonomy: Taxonomy) -> StudentProfile:
    return confirm_understanding(
        empty_profile(),
        result,
        initial_claim_corrections(result),
        initial_academic_corrections(result),
        initial_judgment_corrections(result),
        taxonomy,
    )


def coverage_gaps(
    result: UnderstandingResult, taxonomy: Taxonomy
) -> list[dict[str, str]]:
    """Record unmapped outputs without treating null as proof a node is missing."""
    claims = {item.id: item for item in result.draft.claims}
    rules = {rule.id: rule for rule in taxonomy.evidence_rules}
    gaps = []
    for skill in result.draft.competencies:
        if skill.id not in result.supported_competency_ids:
            continue
        if skill.competency_id is None:
            reason = "unmapped_skill_needs_review"
        elif not any(
            mapping.claim_category == claims[skill.claim_id].category.value
            and rules[mapping.evidence_rule_id].competency_id == skill.competency_id
            for mapping in taxonomy.qualitative_mappings
        ):
            reason = "qualitative_route_missing"
        else:
            continue
        gaps.append(
            {
                "claim_id": skill.claim_id,
                "suggestion_id": skill.id,
                "observed_skill": skill.observed_skill,
                "reason": reason,
            }
        )
    return gaps


def compare(case: GoldenCase, result: UnderstandingResult) -> list[str]:
    """Narrow label/routing oracle, not a complete semantic or factual verifier."""
    if case.claim_expectations:
        return compare_claims(case, result)
    failures = []
    expected_labels = {
        j.dimension: j.label for j in case.expected_understanding.judgments
    }
    actual_labels: dict[str, set[str]] = {}
    for judgment in result.draft.judgments:
        if judgment.id in result.supported_judgment_ids:
            actual_labels.setdefault(judgment.dimension, set()).add(judgment.label)
    for dimension, label in expected_labels.items():
        actual = actual_labels.get(dimension, {"unknown"})
        if (
            actual != {label}
            and case.expected_understanding.claims[0].attribution.value == "student"
        ):
            failures.append(
                f"label:{dimension}: expected {label}, got {','.join(sorted(actual))}"
            )
    actual_skills = {
        s.competency_id
        for s in result.draft.competencies
        if s.id in result.supported_competency_ids and s.competency_id is not None
    }
    expected_skills = {
        s.competency_id
        for s in case.expected_understanding.competencies
        if s.id in case.expected_supported_ids.competencies
        and s.competency_id is not None
    }
    for node in sorted(actual_skills - expected_skills):
        failures.append(f"false_positive_competency:{node}")
    for node in sorted(expected_skills - actual_skills):
        failures.append(f"false_negative_competency:{node}")
    expected_null = [
        s
        for s in case.expected_understanding.competencies
        if s.competency_id is None and s.id in case.expected_supported_ids.competencies
    ]
    actual_null = [
        s
        for s in result.draft.competencies
        if s.competency_id is None and s.id in result.supported_competency_ids
    ]
    if expected_null and not actual_null:
        failures.append("missing_supported_uncatalogued_skill")
    if (
        case.semantic_context.recognized_tools
        and not case.semantic_context.methods_performed
        and result.supported_competency_ids
    ):
        failures.append("tool_recognition_promoted_to_demonstrated_skill")
    if len(result.supported_claim_ids) != len(case.expected_supported_ids.claims):
        failures.append("canonical_claim_count_mismatch")
    if (
        case.unknown_fields
        and all(label == "unknown" for label in expected_labels.values())
        and not result.questions
    ):
        failures.append("missing_clarification")
    return failures


def compare_claims(case: GoldenCase, result: UnderstandingResult) -> list[str]:
    """Compare separately anchored claims; ambiguous alignment cannot pass silently.

    Exact source anchors make these checks reproducible for the curated synthetic
    set. They are not a general semantic matcher for arbitrary student documents.
    """
    failures = []
    if len(result.supported_claim_ids) != len(case.expected_supported_ids.claims):
        failures.append("canonical_claim_count_mismatch")
    for index, expected in enumerate(case.claim_expectations, start=1):
        prefix = f"claim[{index}]"
        matching = [
            claim
            for claim in result.draft.claims
            if claim.id in result.supported_claim_ids
            and any(
                expected.source_quote in citation.quote for citation in claim.citations
            )
        ]
        if len(matching) != 1:
            failures.append(
                f"{prefix}:source_alignment:expected 1, got {len(matching)}"
            )
            continue
        claim = matching[0]
        if claim.attribution != expected.attribution:
            failures.append(
                f"{prefix}:attribution:expected {expected.attribution}, "
                f"got {claim.attribution}"
            )
        if claim.presence != expected.presence:
            failures.append(
                f"{prefix}:presence:expected {expected.presence}, got {claim.presence}"
            )
        if claim.category not in expected.allowed_categories:
            failures.append(f"{prefix}:unsupported_category:{claim.category}")
        skills = [
            s
            for s in result.draft.competencies
            if s.claim_id == claim.id and s.id in result.supported_competency_ids
        ]
        actual_nodes = {s.competency_id for s in skills if s.competency_id is not None}
        allowed_nodes = (
            set(expected.competency_ids)
            | set(expected.optional_competency_ids)
            | set(expected.one_of_competency_ids)
        )
        for node in sorted(actual_nodes - allowed_nodes):
            failures.append(f"{prefix}:false_positive_competency:{node}")
        for node in sorted(set(expected.competency_ids) - actual_nodes):
            failures.append(f"{prefix}:false_negative_competency:{node}")
        if expected.one_of_competency_ids and not actual_nodes.intersection(
            expected.one_of_competency_ids
        ):
            failures.append(
                f"{prefix}:missing_competency_group:"
                f"{','.join(sorted(expected.one_of_competency_ids))}"
            )
        if expected.forbid_skills and skills:
            failures.append(f"{prefix}:context_or_absence_promoted_to_skill")
        if expected.require_uncatalogued_skill and not any(
            s.competency_id is None for s in skills
        ):
            failures.append(f"{prefix}:missing_supported_uncatalogued_skill")
        contexts = {
            (c.kind, c.label.casefold())
            for c in result.draft.contexts
            if c.claim_id == claim.id and c.id in result.supported_context_ids
        }
        for context in expected.contexts:
            if (
                context.exact_label
                and (context.kind, context.label.casefold()) not in contexts
            ) or (
                not context.exact_label
                and not any(kind == context.kind for kind, _ in contexts)
            ):
                failures.append(
                    f"{prefix}:missing_context:{context.kind}:{context.label}"
                )
        for dimension, label in expected.labels.items():
            actual = {
                j.label
                for j in result.draft.judgments
                if j.claim_id == claim.id
                and j.dimension == dimension
                and j.id in result.supported_judgment_ids
            } or {"unknown"}
            if actual != {label}:
                failures.append(
                    f"{prefix}:label:{dimension}:expected {label}, "
                    f"got {','.join(sorted(actual))}"
                )
        if expected.require_clarification and not any(
            q.claim_id == claim.id for q in result.questions
        ):
            failures.append(f"{prefix}:missing_clarification")
        uncertainty = " ".join(result.draft.unassessed).casefold()
        for term in expected.uncertainty_terms:
            if term.casefold() not in uncertainty:
                failures.append(f"{prefix}:missing_uncertainty:{term}")
    return failures


def diagnostics(
    case: GoldenCase, result: UnderstandingResult, taxonomy: Taxonomy
) -> dict:
    profile = project(result, taxonomy)
    competencies = resolve_competencies(profile, taxonomy, as_of=AS_OF)
    contributions = {
        item.competency_id: str(
            sum(
                (
                    t.contribution
                    for t in item.explanation_trace
                    if t.contribution is not None
                ),
                Decimal(0),
            )
        )
        for item in competencies
        if item.explanation_trace
    }
    failures = compare(case, result)
    return {
        "case": case.id,
        "domain": case.domain,
        "strength": case.strength,
        "failures": failures,
        "outcomes": classify_outcomes(failures),
        "coverage_gaps": coverage_gaps(result, taxonomy),
        "mapped_evidence_count": sum(
            e.qualitative_mapping is not None for e in profile.evidence
        ),
        "competency_contributions": contributions or None,
        "taxonomy_version": taxonomy.version,
        "source_is_self_reported": True,
    }


def classify_outcomes(failures: list[str]) -> list[str]:
    """Classify provisional-oracle differences without producing an accuracy score."""
    if not failures:
        return ["structurally_valid", "clean_pass"]
    outcomes = ["structurally_valid"]
    false_positive = any(
        marker in failure
        for failure in failures
        for marker in (
            "false_positive_competency",
            "context_or_absence_promoted_to_skill",
            "tool_recognition_promoted_to_demonstrated_skill",
            "attribution:expected team, got student",
        )
    ) or any("expected unknown, got " in failure for failure in failures)
    false_negative = any(
        marker in failure
        for failure in failures
        for marker in (
            "false_negative_competency",
            "missing_competency_group",
            "missing_context",
            "missing_supported_uncatalogued_skill",
            "missing_clarification",
            "missing_uncertainty",
        )
    ) or any(
        ":expected " in failure and "got unknown" in failure for failure in failures
    )
    if false_positive:
        outcomes.append("semantic_false_positive")
    if false_negative:
        outcomes.append("semantic_false_negative")
    classified = false_positive or false_negative
    if not classified or any(
        marker in failure
        for failure in failures
        for marker in (
            "unsupported_category",
            "source_alignment",
            "canonical_claim_count_mismatch",
        )
    ):
        outcomes.append("reference_disagreement")
    return outcomes


def training_records(case: GoldenCase) -> list[dict]:
    """Export annotated fields, never arithmetic or newly injected model defaults.

    Legacy references have not been adjudicated for typed presence/context. Keep
    their omitted fields omitted instead of silently manufacturing v3 labels.
    """
    schema_version = (
        "understanding-v3"
        if "contexts" in case.expected_understanding.model_fields_set
        and all(
            "presence" in claim.model_fields_set
            for claim in case.expected_understanding.claims
        )
        else "understanding-v2"
    )
    return [
        {
            "case_id": case.id,
            "task": "understanding",
            "input": case.source_text,
            "expected_output": case.expected_understanding.model_dump(
                mode="json", exclude_unset=True
            ),
            "annotation_context": case.semantic_context.model_dump(mode="json"),
            "annotation_status": case.annotation_status,
            "annotation_schema_version": schema_version,
        },
        {
            "case_id": case.id,
            "task": "support_review",
            "input": {
                "source_text": case.source_text,
                "draft": case.review_challenge.draft.model_dump(
                    mode="json", exclude_unset=True
                ),
            },
            "expected_output": case.review_challenge.expected_review.model_dump(
                mode="json"
            ),
            "annotation_status": case.annotation_status,
            "annotation_schema_version": schema_version,
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["recorded", "live"], default="recorded")
    parser.add_argument("--suite", type=Path, default=FIXTURES)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--live-focus", action="store_true")
    selection.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--include-probes", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    suite = load_suite(args.suite)
    available = [*suite.cases, *suite.probes] if args.include_probes else suite.cases
    if args.cases and set(args.cases) - {case.id for case in available}:
        parser.error("Unknown case ID (probes require --include-probes)")
    chosen = (
        available
        if args.all
        else [c for c in available if c.live_focus]
        if args.live_focus
        else [c for c in available if c.id in args.cases]
    )
    taxonomy = load_taxonomy()
    provider_client = (
        CompatibleChatClient.from_environment() if args.mode == "live" else None
    )
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in chosen:
        validate_case(case, taxonomy)
        started = perf_counter()
        case_client = (
            InstrumentedClient(provider_client) if provider_client is not None else None
        )
        try:
            result = interpret(case, taxonomy, client=case_client)
            row = diagnostics(case, result, taxonomy)
            row["validation"] = "passed"
            (args.output / f"{case.id}.json").write_text(
                result.model_dump_json(indent=2), "utf-8"
            )
        except ProviderError as exc:
            message = str(exc)
            outcome = (
                "runtime_failure"
                if "timed out" in message or "endpoint unavailable" in message
                else "structurally_invalid"
            )
            row = {
                "case": case.id,
                "validation": "failed",
                "error": message,
                "outcomes": [outcome],
            }
        except ValueError as exc:
            row = {
                "case": case.id,
                "validation": "failed",
                "error": str(exc),
                "outcomes": ["structurally_invalid"],
            }
        row.update(
            mode=args.mode,
            seconds=round(perf_counter() - started, 2),
            human_review="pending",
        )
        if case_client is not None:
            row["runtime_calls"] = case_client.calls
        rows.append(row)
        (args.output / "results.json").write_text(json.dumps(rows, indent=2), "utf-8")
        print(json.dumps(row), flush=True)
    # Export only reference annotations, never a model's unreviewed completion.
    with (args.output / "training-reference.jsonl").open(
        "w", encoding="utf-8"
    ) as stream:
        for case in chosen:
            for record in training_records(case):
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return int(
        any(row["validation"] != "passed" or row.get("failures") for row in rows)
    )


if __name__ == "__main__":
    raise SystemExit(main())
