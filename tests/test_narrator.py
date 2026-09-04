"""Offline tests for narration over frozen report and assessment data."""

from __future__ import annotations

import warnings
from datetime import date, datetime
from decimal import Decimal

import pytest

from unihive.alternatives import AlternativePathwayResult, ChosenPath
from unihive.llm.narrator import NarrationError, narrate_report
from unihive.models import (
    Assessment,
    CompetencyDemand,
    CompetencyLevel,
    EvidenceState,
    ProgramConfig,
    StudentCompetency,
)
from unihive.report import ReportStructure
from unihive.scoring import (
    ProvisionalScoringWarning,
    load_scoring_configuration,
    score,
)

AS_OF = date(2026, 1, 1)
TIMESTAMP = datetime(2026, 1, 1)


class RecordedNarrationClient:
    """Offline narrator mock that records the exact rendered prompt."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def frozen_inputs() -> tuple[Assessment, ReportStructure]:
    program = ProgramConfig(
        program_id="test-program",
        university="Example University",
        degree="MS",
        demand_profile={
            "programming": CompetencyDemand(
                required_level=CompetencyLevel.PROFICIENT,
                weight=Decimal("1"),
            )
        },
        eligibility_rules=[],
        dimension_emphasis={},
        version="test-v1",
        source_url="https://example.edu/program",
        verified_on=AS_OF,
        provisional=True,
        validated_by=None,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalScoringWarning)
        configuration = load_scoring_configuration()
    assessment = score(
        [
            StudentCompetency(
                competency_id="programming",
                level=CompetencyLevel.PROFICIENT,
                state=EvidenceState.VERIFIED_PRESENT,
                contributing_evidence_ids=["project-e"],
                explanation_trace=[],
            )
        ],
        program,
        taxonomy_version="test-taxonomy-v1",
        engine_version="test-engine-v1",
        timestamp=TIMESTAMP,
        configuration=configuration,
    )
    pathways = AlternativePathwayResult(
        chosen_path=ChosenPath(
            path_id="test-program",
            field="Programming",
            readiness_band=assessment.pathway_readiness,
        ),
        alternatives=[],
        suppressed=[],
    )
    report = ReportStructure(
        what_we_understand_about_you=[],
        strengths=[],
        gaps=[],
        chosen_path_and_alternatives=pathways,
        top_actions=[],
        what_we_cannot_assess_yet=[],
    )
    return assessment, report


def test_narrator_receives_frozen_json_and_returns_prose() -> None:
    assessment, report = frozen_inputs()
    client = RecordedNarrationClient(
        "Your programming evidence meets the expected level for this path."
    )

    result = narrate_report(assessment, report, client)

    assert len(client.prompts) == 1
    assert assessment.model_dump_json() in client.prompts[0]
    assert report.model_dump_json() in client.prompts[0]
    assert "Do not recompute, reorder, re-rank" in client.prompts[0]
    assert result.prose.startswith("Your programming evidence")
    assert result.prompt_version.startswith("narrator-v1:")


@pytest.mark.parametrize(
    "response",
    [
        "You have a 70% admission result.",
        "Your admission chance is strong.",
        "This is a probability statement.",
        "The odds are favorable.",
        "Your likelihood is high.",
    ],
)
def test_narrator_rejects_forbidden_admission_language(response: str) -> None:
    assessment, report = frozen_inputs()
    client = RecordedNarrationClient(response)

    with pytest.raises(NarrationError):
        narrate_report(assessment, report, client)


def test_prompt_forbids_new_facts_and_reordering() -> None:
    assessment, report = frozen_inputs()
    client = RecordedNarrationClient("The supplied report remains unchanged.")

    narrate_report(assessment, report, client)

    prompt = client.prompts[0]
    assert "Use only facts present in the supplied JSON" in prompt
    assert "Never introduce, infer, estimate, or embellish a fact" in prompt
    assert "Preserve the report's six-section order exactly" in prompt
