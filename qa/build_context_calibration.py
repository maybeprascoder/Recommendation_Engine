"""Build a small provisional v3 calibration set from explicitly written scenarios.

This is reference annotation, not observed model output or expert validation.
The original cross-domain-v1 references are preserved separately.
"""

import json
from pathlib import Path

from unihive.understanding import (
    SupportReview,
    UnderstandingDraft,
    complete_unknown_dimensions,
    load_evaluation_rubric,
    supported_context_ids,
    supported_ids,
)


def case(identifier, rows, challenge_target, challenge_kind):
    claims, judgments, skills, contexts, questions, expectations = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    tools, methods = [], []
    for index, row in enumerate(rows, start=1):
        cid = f"c{index}"
        citation = {"document_id": "source", "quote": row["text"]}
        claims.append(
            {
                "id": cid,
                "category": row["category"],
                "statement": row["text"],
                "presence": row.get("presence", "reported_present"),
                "attribution": "student",
                "citations": [citation],
                "duplicate_of": None,
            }
        )
        labels = {
            "ownership": "unknown",
            "depth": "unknown",
            "evaluation": "unknown",
            "impact": "unknown",
            **row.get("labels", {}),
        }
        for dimension, label in labels.items():
            judgments.append(
                {
                    "id": f"j{index}-{dimension}",
                    "claim_id": cid,
                    "dimension": dimension,
                    "label": label,
                    "rationale": row["rationale"],
                    "citations": [citation],
                }
            )
        for tool in row.get("tools", []):
            tools.append(tool)
            contexts.append(
                {
                    "id": f"t{len(contexts) + 1}",
                    "claim_id": cid,
                    "kind": "tool",
                    "label": tool,
                    "rationale": "Named tool or language, independent of skill.",
                    "citations": [citation],
                }
            )
        for skill, node in row.get("skills", []):
            skills.append(
                {
                    "id": f"s{len(skills) + 1}",
                    "claim_id": cid,
                    "competency_id": node,
                    "observed_skill": skill,
                    "rationale": row["rationale"],
                    "citations": [citation],
                }
            )
            methods.append(skill)
        if row.get("question"):
            questions.append(
                {
                    "claim_id": cid,
                    "question": row["question"],
                    "reason": "A tool name does not describe the method performed.",
                }
            )
        expectations.append(
            {
                "source_quote": row["text"],
                "presence": claims[-1]["presence"],
                "allowed_categories": row.get("allowed_categories", [row["category"]]),
                "competency_ids": [node for _, node in row.get("skills", []) if node],
                "contexts": [
                    {"kind": "tool", "label": tool} for tool in row.get("tools", [])
                ],
                "labels": labels,
                "forbid_skills": not row.get("skills"),
                "require_uncatalogued_skill": any(
                    node is None for _, node in row.get("skills", [])
                ),
                "require_clarification": bool(row.get("question")),
            }
        )
    draft = complete_unknown_dimensions(
        UnderstandingDraft.model_validate(
            {
                "claims": claims,
                "academics": [],
                "judgments": judgments,
                "competencies": skills,
                "contexts": contexts,
                "questions": questions,
                "unassessed": [],
            }
        ),
        load_evaluation_rubric(),
    )
    review = SupportReview.model_validate(
        {
            "checks": [
                {
                    "target_id": item.id,
                    "verdict": "supported",
                    "explanation": "Consistent with the source and provisional rubric.",
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
    bad = draft.model_dump(mode="json")
    rejected = []
    if challenge_kind == "tool_skill":
        target = next(c for c in bad["claims"] if c["id"] == challenge_target)
        bad["competencies"].append(
            {
                "id": "bad-tool-skill",
                "claim_id": challenge_target,
                "competency_id": None,
                "observed_skill": "ETABS usage",
                "rationale": "A mentioned tool is a demonstrated skill.",
                "citations": target["citations"],
            }
        )
        rejected = ["bad-tool-skill"]
    elif challenge_kind == "category":
        target = next(c for c in bad["claims"] if c["id"] == challenge_target)
        target["category"] = "coursework"
        rejected = [challenge_target]
    else:
        target = next(
            s for s in bad["competencies"] if s["claim_id"] == challenge_target
        )
        target["competency_id"] = "programming"
        rejected = [target["id"]]
    challenge_review = review.model_dump(mode="json")
    if challenge_kind == "tool_skill":
        challenge_review["checks"].append(
            {
                "target_id": "bad-tool-skill",
                "verdict": "unsupported",
                "explanation": (
                    "The source names a tool but describes no performed method; "
                    "null ID does not make it a demonstrated skill."
                ),
            }
        )
    else:
        for check in challenge_review["checks"]:
            if check["target_id"] in rejected:
                check.update(
                    verdict="unsupported",
                    explanation=(
                        "No course is mentioned; the category invents academic context."
                        if challenge_kind == "category"
                        else "Structural analysis does not establish code writing."
                    ),
                )
    cids, jids, sids = supported_ids(draft, review)
    return {
        "id": identifier,
        "domain": "interdisciplinary",
        "strength": "targeted_v3",
        "source_text": " ".join(row["text"] for row in rows),
        "semantic_context": {
            "domain_concepts": [],
            "recognized_tools": tools,
            "methods_performed": methods,
            "note": (
                "Provisional synthetic annotations for context, scope and routing; "
                "no score targets."
            ),
        },
        "expected_understanding": draft.model_dump(mode="json"),
        "expected_support_review": review.model_dump(mode="json"),
        "expected_supported_ids": {
            "claims": cids,
            "judgments": jids,
            "competencies": sids,
            "contexts": supported_context_ids(draft, review),
        },
        "unknown_fields": sorted(
            {j.dimension for j in draft.judgments if j.label == "unknown"}
        ),
        "coverage_gaps": [
            skill
            for row in rows
            for skill, node in row.get("skills", [])
            if node is None
        ],
        "confirmed_absence": [
            r["text"] for r in rows if r.get("presence") == "reported_absent"
        ],
        "forbidden_inferences": [
            "Tool recognition alone is a skill",
            "Missing publications means missing research ability",
            "Coding requires leadership before a programming suggestion",
            "Invented coursework or employment",
        ],
        "forbidden_competency_ids": ["machine_learning"],
        "annotation_status": "provisional_synthetic_reference",
        "validated_by": None,
        "review_challenge": {
            "draft": bad,
            "expected_review": challenge_review,
            "rejected_ids": rejected,
        },
        "claim_expectations": expectations,
    }


def main():
    tool = {
        "text": "I used ETABS.",
        "category": "activity",
        "tools": ["ETABS"],
        "rationale": (
            "Only a tool is named; no method, result or personal responsibility "
            "is described."
        ),
        "question": "What did you do with ETABS, and which method did you use?",
    }
    absent = {
        "text": "I have no publications.",
        "category": "publication",
        "presence": "reported_absent",
        "rationale": (
            "Explicit publication absence says nothing about research ability "
            "or other work."
        ),
    }
    code = {
        "text": "I wrote Python code to clean survey records.",
        "category": "activity",
        "tools": ["Python"],
        "rationale": (
            "Explicit code writing supports a programming suggestion and applied "
            "depth without implying leadership or measured outcomes."
        ),
        "labels": {"depth": "applied"},
        "skills": [("Python data-cleaning code", "programming")],
    }
    method = {
        "text": (
            "I used ETABS to model a frame and compare member forces "
            "against hand calculations."
        ),
        "category": "activity",
        "allowed_categories": ["activity", "project"],
        "tools": ["ETABS"],
        "rationale": (
            "Modeling and comparing structural forces is a described analysis "
            "method; the taxonomy has no structural-analysis node."
        ),
        "labels": {"depth": "applied", "evaluation": "compared"},
        "skills": [("Structural modeling and force comparison", None)],
    }
    project = {
        **code,
        "text": "For my personal project, I wrote Python code to clean survey records.",
        "category": "project",
    }
    suite = {
        "version": "context-presence-calibration-v1",
        "provisional": True,
        "validated_by": None,
        "source": None,
        "description": (
            "Four provisional v3 references and adversarial support-review targets. "
            "Separate from the historical cross-domain-v1 snapshot."
        ),
        "cases": [
            case("context-mixed", [tool, absent, code], "c3", "category"),
            case("context-tool-only", [tool], "c1", "tool_skill"),
            case("context-performed-method", [method], "c1", "adjacent_node"),
            case("context-programming-project", [project], "c1", "category"),
        ],
        "probes": [],
    }
    path = (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/understanding/context_presence_golden.json"
    )
    path.write_text(
        json.dumps(suite, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
