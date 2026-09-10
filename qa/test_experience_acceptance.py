"""Acceptance gates from the experience document; run explicitly with pytest qa/.

These assert desired product behavior, including currently unimplemented behavior.
They deliberately do not weaken the existing unit-test suite or alter product code.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from test_extractor import RAW_INPUT, VALID_RESPONSE, RecordedClient  # noqa: E402
from test_narrator import RecordedNarrationClient, frozen_inputs  # noqa: E402

import cli  # noqa: E402
import serve  # noqa: E402
from unihive.competency import resolve_competencies  # noqa: E402
from unihive.llm.extractor import (  # noqa: E402
    ExtractionFailedError,
    extract_student_profile,
)
from unihive.llm.narrator import NarrationError, narrate_report  # noqa: E402
from unihive.models import EvidenceState, StudentProfile  # noqa: E402
from unihive.taxonomy import load_taxonomy  # noqa: E402


def test_checkout_has_selectable_profiles_and_programs() -> None:
    assert serve.profiles(), "The profile picker is empty"
    assert serve.programs(), "The program picker is empty"


def test_installed_console_command_can_score_from_checkout() -> None:
    command = Path(sys.executable).parent / "unihive.exe"
    completed = subprocess.run(
        [
            str(command),
            "--score-only",
            "--profile",
            str(ROOT / "tests/fixtures/cli/profile.json"),
            "--program",
            str(ROOT / "tests/fixtures/cli/program.yaml"),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("competency", ["operating_systems", "programming"])
def test_extracted_coursework_and_projects_are_recognized(competency: str) -> None:
    profile = StudentProfile.model_validate_json(VALID_RESPONSE, strict=True)
    resolved = resolve_competencies(profile, load_taxonomy(), as_of=date(2026, 9, 9))
    actual = next(item for item in resolved if item.competency_id == competency)
    assert actual.state is EvidenceState.VERIFIED_PRESENT


def test_cli_supplies_six_section_report(tmp_path: Path, capsys) -> None:
    profile = tmp_path / "profile.json"
    profile.write_text(VALID_RESPONSE, encoding="utf-8")
    assert (
        cli.main(
            [
                "--score-only",
                "--profile",
                str(profile),
                "--program",
                str(ROOT / "tests/fixtures/cli/program.yaml"),
                "--as-of",
                "2026-09-09",
            "--json",
            "--report",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert "report" in payload, "CLI returns Assessment only; web report is unpopulated"
    assert set(payload["report"]) == {
        "what_we_understand_about_you",
        "strengths",
        "gaps",
        "chosen_path_and_alternatives",
        "top_actions",
        "what_we_cannot_assess_yet",
    }


def test_extractor_rejects_claim_unrelated_to_real_source_span() -> None:
    fabricated = json.loads(VALID_RESPONSE)
    fabricated["evidence"][0].update(
        {
            "kind": "machine_learning_publication",
            "raw_text": "First author of a top-tier machine-learning publication",
            "quality": "top_tier_venue",
            "depth": "first_author",
        }
    )
    response = json.dumps(fabricated)
    with pytest.raises(ExtractionFailedError):
        extract_student_profile(RAW_INPUT, RecordedClient([response, response]))


@pytest.mark.parametrize(
    "prose",
    [
        "Your readiness is Emerging and your confidence is Low.",
        "The program deadline is December 31, 2030 and tuition is 12345 dollars.",
    ],
)
def test_narrator_rejects_contradictions_and_unsourced_facts(prose: str) -> None:
    assessment, report = frozen_inputs()
    with pytest.raises(NarrationError):
        narrate_report(assessment, report, RecordedNarrationClient(prose))
