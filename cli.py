"""Command-line entry point for deterministic UniHive assessment and replay."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path

from pydantic import TypeAdapter

from unihive.audit import (
    AuditReplayMismatch,
    create_audited_assessment,
    replay_assessment,
)
from unihive.eligibility import load_program_config
from unihive.followup import build_followup_questions
from unihive.models import Assessment, ProgramConfig, StudentProfile
from unihive.program_quality import assess_programs, load_program_data_policy
from unihive.questions import load_question_bank
from unihive.response import ScoringResponse, build_scoring_response
from unihive.review import ConfirmationRequest, confirm_evidence
from unihive.scoring import LoadedScoringConfiguration, load_scoring_configuration
from unihive.taxonomy import Taxonomy, load_taxonomy
from unihive.understanding_review import (
    UnderstandingReviewRequest,
    initial_academic_corrections,
    initial_claim_corrections,
    initial_judgment_corrections,
    validate_understanding,
)

ENGINE_VERSION = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    """Create the score and replay command-line contract."""
    parser = argparse.ArgumentParser(prog="unihive")
    parser.add_argument(
        "command",
        nargs="?",
        choices=(
            "score",
            "replay",
            "review",
            "review-understanding",
            "confirm",
            "questions",
            "analyze",
            "recommend",
        ),
        default="score",
    )
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="run the deterministic path without an LLM or API key",
    )
    parser.add_argument("--profile", type=Path, help="structured profile JSON")
    parser.add_argument("--program", type=Path, help="sourced program YAML")
    parser.add_argument(
        "--program-dir",
        type=Path,
        help="directory of sourced program YAML files for recommendation screening",
    )
    parser.add_argument(
        "--program-policy",
        type=Path,
        help="versioned program-data freshness policy YAML",
    )
    parser.add_argument(
        "--include-blocked-diagnostics",
        action="store_true",
        help="assess blocked records for diagnostics while keeping them on hold",
    )
    parser.add_argument("--audit", type=Path, help="past assessment JSON to replay")
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        dest="documents",
        help="UTF-8 text document to analyze; repeat for supporting documents",
    )
    parser.add_argument(
        "--recorded-responses",
        type=Path,
        help="offline synthetic/recorded model responses; makes no model calls",
    )
    parser.add_argument(
        "--output", type=Path, help="save analysis JSON exclusively to a new file"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="include the report and eligibility breakdown (requires --json)",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        help="explicit evaluation date in YYYY-MM-DD form",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="emit the assessment as JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a deterministic assessment or replay a past audited assessment."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.report and not args.json_output:
        parser.error("--report requires --json")
    if args.command == "analyze":
        if not args.documents:
            parser.error("analyze requires --input with a UTF-8 text document")
        if args.score_only:
            parser.error("analyze cannot use --score-only")
        from unihive.llm.analysis_cli import run_analysis

        return run_analysis(args.documents, args.recorded_responses, args.output)
    taxonomy = load_taxonomy()
    scoring_configuration = load_scoring_configuration()

    if args.command in {"review", "review-understanding"}:
        interpretation = None
        if args.command == "review-understanding":
            imported = UnderstandingReviewRequest.model_validate_json(
                sys.stdin.read(), strict=True
            )
            profile = imported.profile
            interpretation = imported.understanding
            validate_understanding(interpretation, taxonomy.understanding_version)
        else:
            if args.profile is None:
                parser.error("review requires --profile (use - for stdin)")
            profile = _load_profile(args.profile)

        print(
            json.dumps(
                {
                    "profile": profile.model_dump(mode="json"),
                    "taxonomy_version": taxonomy.version,
                    "mapped_kinds": sorted(
                        {r.evidence_kind for r in taxonomy.evidence_rules}
                    ),
                    "quality_ladders": taxonomy.evidence_configuration[
                        "quality_ladders"
                    ],
                    "depth_factors": taxonomy.evidence_configuration["depth_factors"],
                    **(
                        {
                            "understanding": interpretation.model_dump(mode="json"),
                            "claim_corrections": [
                                change.model_dump(mode="json")
                                for change in initial_claim_corrections(interpretation)
                            ],
                            "academic_corrections": [
                                change.model_dump(mode="json")
                                for change in initial_academic_corrections(
                                    interpretation
                                )
                            ],
                            "judgment_corrections": [
                                change.model_dump(mode="json")
                                for change in initial_judgment_corrections(
                                    interpretation
                                )
                            ],
                        }
                        if interpretation is not None
                        else {}
                    ),
                }
            )
        )
        return 0
    if args.command == "questions":
        response = ScoringResponse.model_validate_json(sys.stdin.read(), strict=True)
        bank = load_question_bank()
        print(
            f"Provisional question banks in use: {int(bank.values.provisional)}",
            file=sys.stderr,
        )
        print(build_followup_questions(response, taxonomy, bank).model_dump_json())
        return 0
    if args.command == "confirm":
        request = ConfirmationRequest.model_validate_json(sys.stdin.read(), strict=True)
        print(confirm_evidence(request, taxonomy).model_dump_json())
        return 0

    if args.command == "recommend":
        if args.profile is None or args.program_dir is None:
            parser.error("recommend requires --profile and --program-dir")
        if not args.program_dir.is_dir():
            parser.error("--program-dir must be a directory")
        program_paths = sorted(args.program_dir.glob("*.yaml"))
        if not program_paths:
            parser.error("--program-dir contains no .yaml program files")
        profile = _load_profile(args.profile)
        programs = [load_program_config(path) for path in program_paths]
        policy = (
            load_program_data_policy(args.program_policy)
            if args.program_policy is not None
            else load_program_data_policy()
        )
        as_of = args.as_of or date.today()
        timestamp = datetime.combine(as_of, time.min, tzinfo=UTC)
        run = assess_programs(
            profile,
            programs,
            taxonomy=taxonomy,
            scoring_configuration=scoring_configuration,
            policy=policy,
            as_of=as_of,
            timestamp=timestamp,
            engine_version=ENGINE_VERSION,
            include_blocked_diagnostics=args.include_blocked_diagnostics,
        )
        provisional_count = (
            _shared_provisional_count(taxonomy, scoring_configuration)
            + sum(item.provisional for item in programs)
            + int(policy.values.provisional)
        )
        print(f"Provisional configs in use: {provisional_count}", file=sys.stderr)
        print(run.model_dump_json(indent=2))
        return 0

    if args.command == "replay":
        if args.audit is None:
            parser.error("replay requires --audit")
        saved = TypeAdapter(Assessment | ScoringResponse).validate_json(
            args.audit.read_text(encoding="utf-8"), strict=True
        )
        expected = saved.assessment if isinstance(saved, ScoringResponse) else saved
        replayed = replay_assessment(
            expected,
            taxonomy=taxonomy,
            scoring_configuration=scoring_configuration,
        )
        program = replayed.audit.program_config_snapshot
        if program is None:
            raise ValueError("replayed audit has no program snapshot")
        response = (
            _report_response(replayed, taxonomy, scoring_configuration)
            if args.report
            else None
        )
        if isinstance(saved, ScoringResponse) and response is not None:
            if saved.model_dump_json() != response.model_dump_json():
                raise AuditReplayMismatch("replayed report is not byte-identical")
        _emit(
            replayed,
            _provisional_count(taxonomy, program, scoring_configuration),
            json_output=args.json_output,
            response=response,
        )
        return 0

    if args.profile is None or args.program is None:
        parser.error("score requires --profile and --program")
    profile = _load_profile(args.profile)
    program = load_program_config(args.program)
    as_of = args.as_of or date.today()
    timestamp = datetime.combine(as_of, time.min, tzinfo=UTC)
    assessment = create_audited_assessment(
        profile,
        program,
        taxonomy=taxonomy,
        scoring_configuration=scoring_configuration,
        as_of=as_of,
        timestamp=timestamp,
        engine_version=ENGINE_VERSION,
    )
    _emit(
        assessment,
        _provisional_count(taxonomy, program, scoring_configuration),
        json_output=args.json_output,
        response=_report_response(assessment, taxonomy, scoring_configuration)
        if args.report
        else None,
    )
    return 0


def _report_response(
    assessment: Assessment,
    taxonomy: Taxonomy,
    scoring: LoadedScoringConfiguration,
) -> ScoringResponse:
    return build_scoring_response(
        assessment,
        taxonomy=taxonomy,
        scoring_configuration=scoring,
    )


def _load_profile(path: Path) -> StudentProfile:
    return StudentProfile.model_validate_json(
        sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8"),
        strict=True,
    )


def _provisional_count(
    taxonomy: Taxonomy,
    program: ProgramConfig,
    scoring: LoadedScoringConfiguration,
) -> int:
    return _shared_provisional_count(taxonomy, scoring) + int(program.provisional)


def _shared_provisional_count(
    taxonomy: Taxonomy,
    scoring: LoadedScoringConfiguration,
) -> int:
    return (
        sum(node.provisional for node in taxonomy.competencies)
        + sum(rule.provisional for rule in taxonomy.evidence_rules)
        + sum(mapping.provisional for mapping in taxonomy.qualitative_mappings)
        + int(taxonomy.evidence_configuration.get("provisional") is True)
        + int(scoring.values.provisional)
    )


def _emit(
    assessment: Assessment,
    provisional_count: int,
    *,
    json_output: bool,
    response: ScoringResponse | None = None,
) -> None:
    count_message = f"Provisional configs in use: {provisional_count}"
    if json_output:
        print(count_message, file=sys.stderr)
        print((response or assessment).model_dump_json(indent=2))
        return

    print(count_message)
    readiness = (
        assessment.pathway_readiness.value
        if assessment.pathway_readiness is not None
        else "NOT_ASSESSED"
    )
    print(f"Pathway readiness: {readiness}")
    print(f"Data confidence: {assessment.data_confidence.value}")
    print(f"Eligibility: {assessment.eligibility.value}")
    print("AuditRecord:")
    print(assessment.audit.model_dump_json(indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
