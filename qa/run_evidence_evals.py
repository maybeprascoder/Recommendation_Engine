"""Run synthetic cases on the configured model; expert review is separate.

Usage: python qa/run_evidence_evals.py --case unpublished-research --output OUTPUT
Repeat --case to choose a bounded subset. All cases require explicit --all.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from evidence_assertions import check_behavior

from unihive.llm.provider import CompatibleChatClient
from unihive.llm.understanding import analyze_documents
from unihive.taxonomy import load_taxonomy
from unihive.understanding import SourceDocument

ROOT = Path(__file__).resolve().parents[1]


class CapturingClient:
    """Keep synthetic raw responses so validation failures can be diagnosed."""

    def __init__(self, inner):
        self.inner = inner
        self.model = inner.model
        self.provider = inner.provider
        self.completions = []

    def complete(self, **kwargs):
        completion = self.inner.complete(**kwargs)
        self.completions.append(asdict(completion))
        return completion


def main() -> int:
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", action="append", dest="cases")
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = json.loads(
        (ROOT / "tests/fixtures/understanding/cases.json").read_text("utf-8")
    )
    if args.cases and set(args.cases) - {case["id"] for case in cases}:
        parser.error("Unknown case ID")
    chosen = cases if args.all else [case for case in cases if case["id"] in args.cases]
    client = CapturingClient(CompatibleChatClient.from_environment())
    taxonomy = load_taxonomy()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for case in chosen:
        client.completions = []
        started = perf_counter()
        record = {
            "case": case["id"],
            "review_expectation": case["review_expectation"],
            "human_review": "pending",
            "model": client.model,
        }
        try:
            result = analyze_documents(
                [SourceDocument(id="document-1", text=case["input"])],
                client,
                taxonomy_version=taxonomy.version,
                competency_catalog={n.id: n.description for n in taxonomy.competencies},
            )
            (args.output / (case["id"] + ".json")).write_text(
                result.model_dump_json(indent=2),
                encoding="utf-8",
            )
            record["validation"] = "passed"
            failures = check_behavior(case["id"], result)
            record["behavior_checks"] = (
                "not_configured"
                if failures is None
                else "failed"
                if failures
                else "passed"
            )
            record["behavior_failures"] = failures or []
        except ValueError as exc:
            record["validation"] = "failed"
            record["error"] = str(exc)
        record["seconds"] = round(perf_counter() - started, 2)
        (args.output / (case["id"] + "-completions.json")).write_text(
            json.dumps(client.completions, indent=2), "utf-8"
        )
        results.append(record)
        print(json.dumps(record), flush=True)
        (args.output / "results.json").write_text(
            json.dumps(results, indent=2), "utf-8"
        )
    return int(
        any(
            record["validation"] == "failed"
            or record.get("behavior_checks") == "failed"
            for record in results
        )
    )


if __name__ == "__main__":
    sys.exit(main())
