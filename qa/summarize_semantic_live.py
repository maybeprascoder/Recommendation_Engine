"""Bundle a focused live run with final provisional-oracle diagnostics.

Model outputs are explicitly labeled and never emitted as training references.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa.cross_domain_evidence import diagnostics, load_suite
from unihive.taxonomy import load_taxonomy
from unihive.understanding import UnderstandingResult


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output already exists; preserve prior live bundles")
    suite = load_suite(args.suite)
    references = {case.id: case for case in suite.cases if case.live_focus}
    rows = json.loads((args.run / "results.json").read_text("utf-8"))
    if len(references) != 14 or len(rows) != 14:
        raise ValueError("Focused semantic live run must contain exactly 14 cases")
    taxonomy = load_taxonomy()
    cases = []
    prompt_versions: set[str] = set()
    prompt_hashes: set[str] = set()
    for original in rows:
        identifier = original["case"]
        reference = references.pop(identifier)
        receipt_path = args.run / f"{identifier}.json"
        item = {
            "case": identifier,
            "source": reference.source_text,
            "annotation_status": reference.annotation_status,
            "human_review": "pending",
            "original_run": original,
            "model_output_is_training_reference": False,
        }
        if receipt_path.exists():
            result = UnderstandingResult.model_validate_json(
                receipt_path.read_text("utf-8")
            )
            prompt_versions.add(result.audit.prompt_version)
            prompt_hashes.add(result.audit.prompt_sha256)
            current = diagnostics(reference, result, taxonomy)
            item.update(
                structural_status="structurally_valid",
                outcomes=current["outcomes"],
                failures=current["failures"],
                current_diagnostics=current,
                model_output=result.model_dump(mode="json"),
            )
        else:
            outcomes = original.get("outcomes", ["structurally_invalid"])
            item.update(
                structural_status=(
                    "runtime_failure"
                    if "runtime_failure" in outcomes
                    else "structurally_invalid"
                ),
                outcomes=outcomes,
                failures=[],
                error=original.get("error"),
                model_output=None,
            )
        cases.append(item)
    if references:
        raise ValueError("Live run omitted focused cases")
    if len(prompt_versions) > 1 or len(prompt_hashes) > 1:
        raise ValueError("Successful live receipts used different prompt contracts")
    payload = {
        "suite_version": suite.version,
        "suite_provisional": suite.provisional,
        "validated_by": suite.validated_by,
        "model_outputs_are_training_references": False,
        "human_review": "pending",
        "prompt_versions_in_successful_receipts": sorted(prompt_versions),
        "prompt_hashes_in_successful_receipts": sorted(prompt_hashes),
        "case_count": len(cases),
        "combined_accuracy": None,
        "cases": cases,
    }
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
