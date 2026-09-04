"""Command-line entry point for deterministic UniHive assessment and replay."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path

from unihive.audit import create_audited_assessment, replay_assessment
from unihive.eligibility import load_program_config
from unihive.models import Assessment, ProgramConfig, StudentProfile
from unihive.scoring import LoadedScoringConfiguration, load_scoring_configuration
from unihive.taxonomy import Taxonomy, load_taxonomy

ENGINE_VERSION = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    """Create the score and replay command-line contract."""
    parser = argparse.ArgumentParser(prog="unihive")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("score", "replay"),
        default="score",
    )
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="run the deterministic path without an LLM or API key",
    )
    parser.add_argument("--profile", type=Path, help="structured profile JSON")
    parser.add_argument("--program", type=Path, help="sourced program YAML")
    parser.add_argument("--audit", type=Path, help="past assessment JSON to replay")
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
    taxonomy = load_taxonomy()
    scoring_configuration = load_scoring_configuration()

    if args.command == "replay":
        if args.audit is None:
            parser.error("replay requires --audit")
        expected = Assessment.model_validate_json(
            args.audit.read_text(encoding="utf-8"), strict=True
        )
        replayed = replay_assessment(
            expected,
            taxonomy=taxonomy,
            scoring_configuration=scoring_configuration,
        )
        program = replayed.audit.program_config_snapshot
        if program is None:
            raise ValueError("replayed audit has no program snapshot")
        _emit(
            replayed,
            _provisional_count(taxonomy, program, scoring_configuration),
            json_output=args.json_output,
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
    )
    return 0


def _load_profile(path: Path) -> StudentProfile:
    return StudentProfile.model_validate_json(
        path.read_text(encoding="utf-8"), strict=True
    )


def _provisional_count(
    taxonomy: Taxonomy,
    program: ProgramConfig,
    scoring: LoadedScoringConfiguration,
) -> int:
    node_count = sum(node.provisional for node in taxonomy.competencies)
    evidence_rule_count = sum(rule.provisional for rule in taxonomy.evidence_rules)
    evidence_configuration_count = int(
        taxonomy.evidence_configuration.get("provisional") is True
    )
    program_count = int(program.provisional)
    scoring_count = int(scoring.values.provisional)
    return (
        node_count
        + evidence_rule_count
        + evidence_configuration_count
        + program_count
        + scoring_count
    )


def _emit(
    assessment: Assessment,
    provisional_count: int,
    *,
    json_output: bool,
) -> None:
    count_message = f"Provisional configs in use: {provisional_count}"
    if json_output:
        print(count_message, file=sys.stderr)
        print(assessment.model_dump_json(indent=2))
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
