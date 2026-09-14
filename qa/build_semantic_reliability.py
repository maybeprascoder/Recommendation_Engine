"""Generate provisional qualitative references for semantic-reliability testing.

The cases are synthetic human-authored targets. They contain no numeric scores,
program data, target relevance, or model-generated labels.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from unihive.understanding import (
    CompetencySuggestion,
    SupportReview,
    SupportVerdict,
    UnderstandingDraft,
    complete_unknown_dimensions,
    load_evaluation_rubric,
    supported_context_ids,
    supported_ids,
)


class ContextSpec(TypedDict, total=False):
    kind: str
    label: str
    exact_label: bool


class SkillSpec(TypedDict):
    label: str
    competency_id: str | None


class CaseSpec(TypedDict, total=False):
    id: str
    domain: str
    text: str
    category: str
    attribution: str
    allowed_categories: list[str]
    presence: str
    labels: dict[str, str]
    contexts: list[ContextSpec]
    skills: list[SkillSpec]
    required_competency_ids: list[str]
    optional_competency_ids: list[str]
    one_of_competency_ids: list[str]
    forbid_skills: bool
    question: str
    live_focus: bool
    unassessed: list[str]


UNKNOWN_LABELS = {
    "ownership": "unknown",
    "depth": "unknown",
    "evaluation": "unknown",
    "impact": "unknown",
}


def _case(spec: CaseSpec) -> dict[str, object]:
    text = spec["text"]
    citation = {"document_id": "source", "quote": text}
    labels = {**UNKNOWN_LABELS, **spec.get("labels", {})}
    contexts = [
        {
            "id": f"t{index}",
            "claim_id": "c1",
            "kind": item["kind"],
            "label": item["label"],
            "rationale": "Explicit source terminology retained as context.",
            "citations": [citation],
        }
        for index, item in enumerate(spec.get("contexts", []), start=1)
    ]
    skills = [
        {
            "id": f"s{index}",
            "claim_id": "c1",
            "competency_id": item["competency_id"],
            "observed_skill": item["label"],
            "rationale": "The source states the performed method or skill.",
            "citations": [citation],
        }
        for index, item in enumerate(spec.get("skills", []), start=1)
    ]
    draft = complete_unknown_dimensions(
        UnderstandingDraft.model_validate(
            {
                "claims": [
                    {
                        "id": "c1",
                        "category": spec.get("category", "activity"),
                        "statement": text,
                        "attribution": spec.get("attribution", "student"),
                        "presence": spec.get("presence", "reported_present"),
                        "citations": [citation],
                        "duplicate_of": None,
                    }
                ],
                "academics": [],
                "judgments": [
                    {
                        "id": f"j-{dimension}",
                        "claim_id": "c1",
                        "dimension": dimension,
                        "label": label,
                        "rationale": "Provisional semantic-boundary annotation.",
                        "citations": [citation],
                    }
                    for dimension, label in labels.items()
                ],
                "competencies": skills,
                "contexts": contexts,
                "questions": (
                    [
                        {
                            "claim_id": "c1",
                            "question": spec["question"],
                            "reason": (
                                "The source does not establish a performed method."
                            ),
                        }
                    ]
                    if spec.get("question")
                    else []
                ),
                "unassessed": spec.get("unassessed", []),
            }
        ),
        load_evaluation_rubric(),
    )
    review = _supported_review(draft)
    challenge, challenge_review, rejected = _challenge(draft, review, spec)
    claims, judgments, competencies = supported_ids(draft, review)
    tools = [c["label"] for c in spec.get("contexts", []) if c["kind"] == "tool"]
    concepts = [c["label"] for c in spec.get("contexts", []) if c["kind"] != "tool"]
    return {
        "id": spec["id"],
        "domain": spec["domain"],
        "strength": "semantic_boundary_v1",
        "source_text": text,
        "semantic_context": {
            "domain_concepts": concepts,
            "recognized_tools": tools,
            "methods_performed": [item["label"] for item in spec.get("skills", [])],
            "note": (
                "Provisional synthetic semantic target; model output is stored only "
                "in separate live-run artifacts."
            ),
        },
        "expected_understanding": draft.model_dump(mode="json"),
        "expected_support_review": review.model_dump(mode="json"),
        "expected_supported_ids": {
            "claims": claims,
            "judgments": judgments,
            "competencies": competencies,
            "contexts": supported_context_ids(draft, review),
        },
        "unknown_fields": sorted(
            {item.dimension for item in draft.judgments if item.label == "unknown"}
        ),
        "coverage_gaps": [
            item["label"]
            for item in spec.get("skills", [])
            if item["competency_id"] is None
        ],
        "confirmed_absence": (
            [text] if spec.get("presence") == "reported_absent" else []
        ),
        "forbidden_inferences": _forbidden(spec),
        "forbidden_competency_ids": [],
        "annotation_status": "provisional_human_authored_synthetic_reference",
        "validated_by": None,
        "review_challenge": {
            "draft": challenge.model_dump(mode="json"),
            "expected_review": challenge_review.model_dump(mode="json"),
            "rejected_ids": rejected,
        },
        "claim_expectations": [
            {
                "source_quote": text,
                "attribution": spec.get("attribution", "student"),
                "presence": spec.get("presence", "reported_present"),
                "allowed_categories": spec.get(
                    "allowed_categories", [spec.get("category", "activity")]
                ),
                "competency_ids": [
                    *spec.get(
                        "required_competency_ids",
                        [
                            item["competency_id"]
                            for item in spec.get("skills", [])
                            if item["competency_id"] is not None
                        ],
                    )
                ],
                "optional_competency_ids": spec.get(
                    "optional_competency_ids", []
                ),
                "one_of_competency_ids": spec.get("one_of_competency_ids", []),
                "contexts": spec.get("contexts", []),
                "labels": labels,
                "forbid_skills": spec.get("forbid_skills", False),
                "require_uncatalogued_skill": any(
                    item["competency_id"] is None for item in spec.get("skills", [])
                ),
                "require_clarification": bool(spec.get("question")),
                "uncertainty_terms": (
                    ["venue", "acceptance", "citation"]
                    if spec["id"].startswith("publication-")
                    else []
                ),
            }
        ],
        "live_focus": spec.get("live_focus", False),
    }


def _supported_review(draft: UnderstandingDraft) -> SupportReview:
    return SupportReview.model_validate(
        {
            "checks": [
                {
                    "target_id": item.id,
                    "verdict": "supported",
                    "explanation": "Matches the provisional source-grounded target.",
                }
                for item in [
                    *draft.claims,
                    *draft.judgments,
                    *draft.competencies,
                    *draft.contexts,
                ]
            ]
        }
    )


def _challenge(
    draft: UnderstandingDraft, review: SupportReview, spec: CaseSpec
) -> tuple[UnderstandingDraft, SupportReview, list[str]]:
    challenge = draft.model_copy(deep=True)
    target_id: str
    identifier = spec["id"]
    if identifier.startswith("publication-unspecified"):
        item = next(j for j in challenge.judgments if j.dimension == "evaluation")
        item = item.model_copy(update={"label": "externally_reviewed"})
        challenge = challenge.model_copy(
            update={
                "judgments": [
                    item if value.dimension == "evaluation" else value
                    for value in challenge.judgments
                ]
            }
        )
        target_id = item.id
    elif identifier.startswith("ownership-"):
        item = next(j for j in challenge.judgments if j.dimension == "ownership")
        replacement = "led" if item.label == "unknown" else "unknown"
        item = item.model_copy(update={"label": replacement})
        challenge = challenge.model_copy(
            update={
                "judgments": [
                    item if value.dimension == "ownership" else value
                    for value in challenge.judgments
                ]
            }
        )
        target_id = item.id
    elif labels := spec.get("labels"):
        if labels.get("impact", "unknown") == "unknown":
            item = next(j for j in challenge.judgments if j.dimension == "impact")
            item = item.model_copy(update={"label": "reported"})
            challenge = challenge.model_copy(
                update={
                    "judgments": [
                        item if value.dimension == "impact" else value
                        for value in challenge.judgments
                    ]
                }
            )
            target_id = item.id
        elif labels.get("ownership", "unknown") == "unknown":
            item = next(j for j in challenge.judgments if j.dimension == "ownership")
            item = item.model_copy(update={"label": "led"})
            challenge = challenge.model_copy(
                update={
                    "judgments": [
                        item if value.dimension == "ownership" else value
                        for value in challenge.judgments
                    ]
                }
            )
            target_id = item.id
        else:
            challenge, target_id = _add_false_skill(challenge, draft)
    elif spec.get("presence") == "reported_absent" or spec.get("forbid_skills"):
        challenge, target_id = _add_false_skill(challenge, draft)
    else:
        challenge, target_id = _add_false_skill(challenge, draft)
    checks = []
    for check in _supported_review(challenge).checks:
        if check.target_id == target_id:
            check = check.model_copy(
                update={
                    "verdict": SupportVerdict.UNSUPPORTED,
                    "explanation": "The proposal exceeds the exact source proposition.",
                }
            )
        checks.append(check)
    return challenge, review.model_copy(update={"checks": checks}), [target_id]


def _add_false_skill(
    challenge: UnderstandingDraft, source: UnderstandingDraft
) -> tuple[UnderstandingDraft, str]:
    existing = {item.competency_id for item in source.competencies}
    competency_id = (
        "machine_learning" if "machine_learning" not in existing else "security"
    )
    suggestion = CompetencySuggestion(
        id="s-unsupported",
        claim_id="c1",
        competency_id=competency_id,
        observed_skill="Inferred adjacent competency",
        rationale="This is deliberately unsupported for reviewer regression.",
        citations=source.claims[0].citations,
    )
    data = [*challenge.competencies, suggestion]
    return challenge.model_copy(update={"competencies": data}), "s-unsupported"


def _forbidden(spec: CaseSpec) -> list[str]:
    result = ["No venue prestige, acceptance rate, or citation count may be invented."]
    labels = spec.get("labels", {})
    if labels.get("impact", "unknown") == "unknown":
        result.append("Evaluation activity must not be promoted to impact.")
    if labels.get("ownership", "unknown") == "unknown":
        result.append("Personal execution must not be promoted to leadership.")
    if spec.get("presence") == "reported_absent":
        result.append("Absence must not be broadened beyond the cited proposition.")
    if spec.get("forbid_skills"):
        result.append("Context alone must not become a demonstrated skill.")
    return result


def _comparison_specs() -> list[CaseSpec]:
    return [
        {
            "id": f"evaluation-{domain}",
            "domain": domain,
            "text": text,
            "labels": {"evaluation": "compared"},
            "live_focus": domain == "civil",
        }
        for domain, text in [
            ("civil", "Compared forces under two load cases."),
            ("cybersecurity", "Compared alerts from two tools."),
            ("machine_learning", "Compared three models."),
            ("mechanical", "Compared three design variants."),
            ("electrical", "Compared two filtering approaches."),
        ]
    ]


def _impact_specs() -> list[CaseSpec]:
    return [
        {
            "id": "impact-evaluation-only",
            "domain": "machine_learning",
            "text": "Compared four models.",
            "labels": {"evaluation": "compared"},
        },
        {
            "id": "impact-reported-outcome",
            "domain": "software",
            "text": "The new workflow made deployment easier.",
            "labels": {"impact": "reported"},
            "forbid_skills": True,
        },
        {
            "id": "impact-measured-outcome",
            "domain": "software",
            "text": "Reduced deployment time by 35%.",
            "labels": {"impact": "measured"},
            "forbid_skills": True,
        },
        {
            "id": "impact-adopted",
            "domain": "software",
            "text": "The tool was adopted by the deployment team.",
            "labels": {"impact": "adopted"},
            "forbid_skills": True,
        },
        {
            "id": "impact-civil-measured",
            "domain": "civil",
            "text": "Compared two beam designs and reduced material usage by 12%.",
            "labels": {
                "depth": "applied",
                "evaluation": "compared",
                "impact": "measured",
            },
            "skills": [
                {
                    "label": "Structural design comparison",
                    "competency_id": "structural_analysis",
                }
            ],
            "contexts": [
                {
                    "kind": "domain",
                    "label": "civil engineering",
                    "exact_label": False,
                }
            ],
            "live_focus": True,
        },
    ]


def _ownership_specs() -> list[CaseSpec]:
    specs: list[CaseSpec] = []
    for verb in ("Designed", "Implemented", "Developed", "Built", "Created"):
        specs.append(
            {
                "id": f"ownership-execution-{verb.lower()}",
                "domain": "software",
                "text": f"{verb} a data-ingestion service.",
                "allowed_categories": ["activity", "project"],
                "labels": {"depth": "applied"},
                "skills": [
                    {"label": "Software implementation", "competency_id": "programming"}
                ],
            }
        )
    leadership = [
        (
            "ownership-led-team",
            "Led a team of four engineers building a data-ingestion service.",
        ),
        (
            "ownership-owned-delivery",
            "Owned the design and implementation of a data-ingestion service.",
        ),
        ("ownership-sole-delivery", "Solely developed the data-ingestion service."),
        (
            "ownership-project-lead",
            "Served as project lead for the data-ingestion service.",
        ),
    ]
    for identifier, text in leadership:
        specs.append(
            {
                "id": identifier,
                "domain": "software",
                "text": text,
                "allowed_categories": ["activity", "project"],
                "labels": {"ownership": "led"},
                "live_focus": identifier == "ownership-led-team",
            }
        )
    specs.append(
        {
            "id": "ownership-team-ambiguous",
            "domain": "software",
            "text": "Our team built a data-ingestion service.",
            "attribution": "team",
            "allowed_categories": ["activity", "project"],
            "labels": {},
            "forbid_skills": True,
            "question": "What did you personally contribute to the team project?",
            "live_focus": True,
        }
    )
    return specs


def _publication_specs() -> list[CaseSpec]:
    common: CaseSpec = {
        "domain": "research",
        "category": "publication",
        "contexts": [{"kind": "concept", "label": "Journal XYZ"}],
        "forbid_skills": True,
        "unassessed": [
            "Venue quality, acceptance rate and citation impact are unknown."
        ],
        "live_focus": True,
    }
    return [
        {
            **common,
            "id": "publication-unspecified-review",
            "text": "Published a paper in Journal XYZ.",
            "labels": {},
        },
        {
            **common,
            "id": "publication-explicit-peer-review",
            "text": "Published a peer-reviewed paper in Journal XYZ.",
            "labels": {"evaluation": "externally_reviewed"},
        },
    ]


def _absence_specs() -> list[CaseSpec]:
    return [
        {
            "id": "absence-python",
            "domain": "software",
            "text": "I have never used Python.",
            "presence": "reported_absent",
            "contexts": [{"kind": "tool", "label": "Python"}],
            "forbid_skills": True,
            "live_focus": True,
        },
        {
            "id": "absence-publication",
            "domain": "research",
            "text": "I have no publications.",
            "category": "publication",
            "presence": "reported_absent",
            "forbid_skills": True,
            "live_focus": True,
        },
        {
            "id": "absence-internship",
            "domain": "work",
            "text": "I have no internship experience.",
            "category": "work",
            "presence": "reported_absent",
            "forbid_skills": True,
        },
    ]


def _mixed_specs() -> list[CaseSpec]:
    return [
        {
            "id": "mixed-civil-python",
            "domain": "civil",
            "text": "Wrote Python scripts to calculate structural loads.",
            "labels": {"depth": "applied"},
            "contexts": [
                {"kind": "tool", "label": "Python"},
                {
                    "kind": "domain",
                    "label": "structural load calculation",
                    "exact_label": False,
                },
            ],
            "skills": [
                {"label": "Python scripting", "competency_id": "programming"},
                {
                    "label": "Structural load calculation",
                    "competency_id": "structural_analysis",
                },
            ],
            "live_focus": True,
        },
        {
            "id": "mixed-cyber-python",
            "domain": "cybersecurity",
            "text": "Built a Python parser for malicious packet captures.",
            "allowed_categories": ["activity", "project"],
            "labels": {"depth": "applied"},
            "contexts": [
                {"kind": "tool", "label": "Python"},
                {
                    "kind": "domain",
                    "label": "malicious packet analysis",
                    "exact_label": False,
                },
            ],
            "skills": [
                {
                    "label": "Python parser implementation",
                    "competency_id": "programming",
                },
                {"label": "Malicious packet analysis", "competency_id": "security"},
            ],
            "required_competency_ids": ["programming"],
            "optional_competency_ids": ["security", "networking"],
            "one_of_competency_ids": ["security", "networking"],
            "live_focus": True,
        },
        {
            "id": "mixed-mechanical-matlab",
            "domain": "mechanical",
            "text": "Implemented MATLAB optimization routines for a suspension model.",
            "labels": {"depth": "applied"},
            "contexts": [
                {"kind": "tool", "label": "MATLAB"},
                {
                    "kind": "domain",
                    "label": "suspension optimization",
                    "exact_label": False,
                },
            ],
            "skills": [
                {
                    "label": "Optimization routine implementation",
                    "competency_id": "programming",
                },
                {
                    "label": "Suspension modeling",
                    "competency_id": "engineering_simulation",
                },
            ],
        },
        {
            "id": "mixed-ml-strong",
            "domain": "machine_learning",
            "text": (
                "Trained three PyTorch classifiers, compared held-out F1 scores, "
                "and reduced false positives by 18%."
            ),
            "labels": {
                "depth": "investigated",
                "evaluation": "compared",
                "impact": "measured",
            },
            "contexts": [{"kind": "tool", "label": "PyTorch"}],
            "skills": [
                {
                    "label": "Classifier training and evaluation",
                    "competency_id": "machine_learning",
                }
            ],
            "live_focus": True,
        },
    ]


def _tool_specs() -> list[CaseSpec]:
    definitions = [
        (
            "etabs",
            "ETABS",
            "modeled a frame",
            "Structural modeling",
            "structural_analysis",
        ),
        (
            "autocad",
            "AutoCAD",
            "created dimensioned drawings",
            "Technical drafting",
            None,
        ),
        (
            "ansys",
            "ANSYS",
            "ran a stress simulation",
            "Finite-element simulation",
            "engineering_simulation",
        ),
        (
            "solidworks",
            "SolidWorks",
            "modeled an assembly",
            "Mechanical CAD modeling",
            "mechanical_design",
        ),
        (
            "matlab",
            "MATLAB",
            "implemented a numerical solver",
            "Numerical programming",
            "programming",
        ),
        (
            "arduino",
            "Arduino",
            "wrote sensor firmware",
            "Firmware programming",
            "programming",
        ),
        (
            "verilog",
            "Verilog",
            "wrote a counter module",
            "Hardware-description programming",
            "programming",
        ),
        (
            "wireshark",
            "Wireshark",
            "analyzed packet captures",
            "Packet analysis",
            "networking",
        ),
        (
            "nessus",
            "Nessus",
            "ran an authenticated scan and reviewed findings",
            "Vulnerability assessment",
            "security",
        ),
        (
            "kali",
            "Kali Linux",
            "performed a lab penetration test",
            "Security testing",
            "security",
        ),
        (
            "tensorflow",
            "TensorFlow",
            "trained an image classifier",
            "Model training",
            "machine_learning",
        ),
        (
            "pytorch",
            "PyTorch",
            "trained a text classifier",
            "Model training",
            "machine_learning",
        ),
        (
            "react",
            "React",
            "implemented an interactive interface",
            "Interface programming",
            "programming",
        ),
        (
            "sql",
            "SQL",
            "wrote joins to transform records",
            "Query programming",
            "programming",
        ),
        ("aws", "AWS", "configured a container deployment", "Cloud deployment", None),
        (
            "python",
            "Python",
            "wrote a data-cleaning script",
            "Python programming",
            "programming",
        ),
    ]
    specs: list[CaseSpec] = []
    for slug, tool, action, skill, node in definitions:
        specs.extend(
            [
                {
                    "id": f"tool-{slug}-bare",
                    "domain": "tool_consistency",
                    "text": f"Tools: {tool}.",
                    "contexts": [{"kind": "tool", "label": tool}],
                    "forbid_skills": True,
                    "question": f"What did you personally do with {tool}?",
                    "live_focus": slug in {"etabs", "nessus", "pytorch"},
                },
                {
                    "id": f"tool-{slug}-activity",
                    "domain": "tool_consistency",
                    "text": f"Used {tool} and {action}.",
                    "labels": {"depth": "applied"},
                    "contexts": [{"kind": "tool", "label": tool}],
                    "skills": [{"label": skill, "competency_id": node}],
                },
                {
                    "id": f"tool-{slug}-independent",
                    "domain": "tool_consistency",
                    "text": f"Solely owned the task: I used {tool} and {action}.",
                    "labels": {"ownership": "led", "depth": "applied"},
                    "contexts": [{"kind": "tool", "label": tool}],
                    "skills": [{"label": skill, "competency_id": node}],
                },
            ]
        )
    return specs


def main() -> None:
    specs = [
        *_comparison_specs(),
        *_impact_specs(),
        *_ownership_specs(),
        *_publication_specs(),
        *_absence_specs(),
        *_mixed_specs(),
        *_tool_specs(),
    ]
    ids = [item["id"] for item in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("Semantic reliability case IDs must be unique")
    if sum(bool(item.get("live_focus")) for item in specs) != 14:
        raise ValueError("Focused live set must contain exactly 14 cases")
    suite = {
        "version": "semantic-reliability-v1",
        "provisional": True,
        "validated_by": None,
        "source": None,
        "description": (
            "Human-authored synthetic semantic boundaries. Provisional until "
            "expert adjudication; no model-generated output is a target."
        ),
        "cases": [_case(item) for item in specs],
        "probes": [],
    }
    destination = (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/understanding/semantic_reliability.json"
    )
    destination.write_text(
        json.dumps(suite, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
