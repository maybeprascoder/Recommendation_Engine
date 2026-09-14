# Context calibration follow-up — 2026-09-13

This continues the typed context/presence work in `CONTEXT_AND_PRESENCE.md`.
The existing pipeline and scoring configuration remain intact.

## Changes

1. The existing QA runner accepts `--suite` and optional claim-level expectations.
   Each expectation is anchored to an exact synthetic source passage. Checks cover
   presence, allowed category, context, skill routing, qualitative labels and
   clarification on that claim. Another claim's correct skill or label cannot
   mask an error. Missing or ambiguous source alignment is reported separately;
   this is not a general semantic matcher for arbitrary documents.
2. Four provisional v3 reference cases plus adversarial support-review targets
   exercise mixed tool/absence/code evidence, a tool-only statement, an actual
   structural-analysis method, and an explicitly stated programming project.
   `build_context_calibration.py` generates the reviewable fixture
   `tests/fixtures/understanding/context_presence_golden.json`. The historical
   cross-domain-v1 annotation snapshot is preserved separately.
3. v7 prompts distinguish tool context from demonstrated skills even when the
   proposed skill has a null ID. Naming an evidenced skill does not require
   leadership or advanced mastery. Categories must preserve stated setting:
   no invented coursework/employment, and publication absence is not research
   absence. These are instructions to the existing two model passes, not a
   deterministic keyword classifier or a third evaluator.
4. Null-ID diagnostics now say `unmapped_skill_needs_review`. A null suggestion
   does not prove a missing taxonomy node; it may be a model routing error or
   an inappropriate suggestion. Configured route absence remains separately
   identified as `qualitative_route_missing`.

## Reproduction

```powershell
.venv/Scripts/python.exe -m qa.cross_domain_evidence --suite tests/fixtures/understanding/context_presence_golden.json --all --output data/reviews/context-v3-recorded-NEW
```

For live evaluation, configure the existing provider and add `--mode live`.
Every run requires a fresh output directory. References are marked provisional
and pending human validation. The eight exported training-reference records
contain qualitative targets only; numeric projection diagnostics stay separate.
No training was performed.

Exports preserve only explicitly annotated fields and include the annotation
schema version. Loading an old reference into a newer runtime must not silently
add `reported_present` or empty context targets to training data. Legacy exports
therefore remain v2 annotations until human-reviewed migration; the new four
references carry explicit v3 targets.

## Baseline and recorded evidence

The new oracle was applied to the saved v6 live result, without rerunning or
rewriting it. It detected all four observed problems:

- Tool-only ETABS usage was accepted as a skill.
- Publication absence was categorized as research.
- Unspecified Python work was categorized as coursework.
- The coding claim did not suggest the existing programming node.

See `context-calibration-v6-baseline.json`. This is a narrow provisional oracle,
not a claim of complete semantic verification.

All four recorded references pass. The tool and structural-method cases receive
no mapped score. The mixed input preserves absence, recognizes Python programming,
and has no mapping for the unspecified activity category. The explicit programming
project qualifies for one existing provisional mapping. A correct skill does not
guarantee an available scoring route, and no extra route was invented here.

The four recorded adversarial reviews reject fabricated academic categories,
tool-only null skills, or structural software use routed to programming. Together
with historical cases and deliberate oracle mutations, **169 tests passed**.
The final export-preservation regression also passed all **169 tests**. Logs are
`context-calibration-tests.txt` and `context-calibration-final-tests.txt`.

## Live v7 outcome

One four-case run used the existing local `qwen3.5:9b` Ollama adapter with context
16384 and a 180-second per-call timeout. No retries or model downloads occurred.

| Case | Outcome | Interpretation |
| --- | --- | --- |
| Mixed tool, absence and coding | Endpoint timeout at 180.08 seconds | No semantic conclusion; the combined v6 errors are not yet shown to be fixed. |
| Tool-only ETABS | Targeted checks passed, 76.52 seconds | Context retained, all dimensions unknown, no skill credit, clarification supplied. |
| Performed structural method | Schema/provenance passed; impact check failed, 145.71 seconds | Skill preserved as unmapped; the model and reviewer still mistook a reported action for reported impact. No scoring mapping activated. |
| Explicit programming project | Targeted checks passed, 115.98 seconds | Programming suggestion retained and one existing mapping activated. Reviewer rejected an extra quantitative-analysis suggestion that the source did not establish. |

The two passing cases concern the **supported final interpretation**, not every
first-pass proposal. In the project case, the draft still overreached before its
second review. In the structural-method case, both passes explicitly acknowledged
no outcome was stated yet accepted `impact=reported`; the correct reference is
unknown. This is an observed semantic failure, not a numeric-scoring failure.

`context-calibration-live-results.json` preserves original run rows, complete
successful receipts and diagnostics recomputed with the final QA code. Original
rows predate the diagnostic reason rename and remain unchanged for audit.
`context-calibration-live-v7.txt` preserves the process output. These results do
not establish general model reliability or success on the combined mixed case.

Ruff, strict mypy (19 source files), and all **14 frontend checks** passed; logs
are `context-calibration-{ruff,mypy,frontend}.txt`. Full-suite output is retained
in `context-calibration-pytest.txt`.

## Limits and remaining work

The annotations are synthetic and await expert review. Exact citation anchors
and allowed-category sets make disagreements inspectable; a mismatch can reflect
annotation granularity rather than hallucination. No overall model-accuracy
claim follows from these tests. Review of null suggestions and missing routes,
ownership/peer-review errors, broader repeated live evaluations and human mapping
calibration remain necessary.
