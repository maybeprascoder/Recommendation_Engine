# Context and explicit presence — 2026-09-13

## Delivered

The existing interpretation → support review → student confirmation → deterministic
mapping pipeline now carries typed context and claim presence. No new evaluator,
taxonomy nodes, mappings, scoring coefficients or program data were added in this step.

- `UnderstandingDraft.contexts` holds cited tool, domain and concept recognition.
  Context IDs share the global ID namespace and exact citation/reference checks.
  The existing second model reviews every context exactly once. Supported context
  also requires a supported canonical parent claim. Team context can be retained
  without granting the student skill credit.
- Context is visible in the review screen and preserved in the complete receipt.
  It never becomes a competency suggestion or a mapping input automatically.
  Context corrections can be recorded in the claim notes; there is no separate
  context confirmation or scoring route.
- Each claim has `presence`: `reported_present`, `reported_absent` or `unknown`.
  New model responses must explicitly supply it. Missing document information
  should not generate absent claims. Prompts require narrow absence scope and
  separate positive accomplishments from different explicitly denied activities.
- Positive judgments and competency suggestions attached to absent or unknown
  claims cannot enter mapping, even if the second model accepts those proposals.
  They remain inspectable in the original interpretation.
- Confirming an unchanged, supported personal absence creates source-linked
  `CONFIRMED_ABSENT` Evidence. Unknown presence remains `UNKNOWN`. These generic
  records remain excluded from scoring. In particular, “no publications” does
  not establish “no research” or “no ML ability.” No competency-level absence
  mapping was invented.
- Presence edits, like statement and attribution edits, require another support
  review before import. Rejected claims cannot be promoted by student confirmation.
  The automatic depth question is omitted for explicitly absent activities.
- New results are `understanding-v3`, with v6 interpretation/review prompts.
  Old v2 results remain readable with their original present default and empty
  contexts. Their canonical receipt fingerprints remain unchanged so reconfirming
  an old receipt does not duplicate its imported evidence. v2 results cannot carry
  the new non-default presence or context semantics.

## Verification

Recorded tests exercise schema and deterministic boundaries, not model accuracy.
They cover all 14 named tool probes, exact context provenance, missing and duplicate
reviews, parent rejection, edited presence, unknown versus absence, mixed positive
work and separate absence, positive proposals on non-present claims, ID collisions,
and old receipt fingerprint compatibility. The live HTTP regression covers review,
confirmation, downloaded receipts, reopening and exclusion from scoring.

- Full suite before the final omission guard: **431 passed** in 104.09 seconds.
  Log: `context-presence-pytest.txt`.
- Additional HTTP persistence regression: **1 passed**.
  Log: `context-presence-http.txt`.
- Final affected-suite regression, including the omission guard: **244 passed**
  in 48.72 seconds. Log: `context-presence-final-regressions.txt`. Together these
  runs cover all 433 current tests; the last run targets the changed boundaries
  rather than repeating unrelated checks.
- Ruff, strict mypy (19 source files) and 14 frontend contracts: see
  `context-presence-{ruff,mypy,frontend}.txt`.

## Remaining work

This supplies a clearer representation and hard scoring boundaries; it does not
prove correct model interpretation. A model can still misclassify negation,
incorrectly suggest a skill in parallel with context, overclaim ownership or
infer peer review. Both model passes can repeat the same semantic error.

The prior 54-case cross-domain reference set remains an explicitly provisional
historical annotation snapshot. Its context and absence sidecars have not been
silently relabeled as expert-validated v3 targets. Next calibration work should
adjudicate and version those targets for the new fields, repeat live cases, and
measure context/skill separation and absence scope separately. Mapping calibration
and missing discipline coverage still need human evidence and validation.

## Live smoke

The synthetic input is `context-presence-input.txt`: a tool mention, explicit
publication absence and a separate code-writing activity. It uses the existing
local Ollama adapter with `qwen3.5:9b`, context 16384 and 180-second per-call timeout.
The process log is `context-presence-live.txt`; the complete source-linked result
is `context-presence-live-result.json`. One attempt completed both model calls
and passed schema/provenance checks. Manual inspection found mixed behavior:

| Check | Observed result |
| --- | --- |
| Typed absence | “I have no publications” retained as `reported_absent`, all dimensions unknown, no skill attached. |
| Context | ETABS, Python and data-cleaning context created and reviewed. |
| Unknown tool depth | ETABS depth remained unknown; clarification supplied. |
| Context versus skill | Failed: ETABS usage also appeared as supported null-ID skill `s2`, despite no described method. |
| Existing-node routing | Failed: explicit Python coding remained null-ID, with an unjustified scope/ownership prerequisite for the programming node. |
| Category fidelity | Failed: publication absence categorized as research, and coding categorized as coursework without course evidence. |
| Confirmation boundary | Replaying confirmation preserved one absent record and two self-reported records, all excluded from scoring; no mappings activated. |

The projection is `context-presence-live-projection.json`. These are synthetic
QA artifacts, not changes to a student's saved profile. This smoke supports the
typed-absence path but does **not** pass overall semantic calibration. The model
still needs better tool/skill separation, source-grounded category selection and
catalog routing. No keyword patch or automatic numeric credit was added to hide
those failures. Ownership and peer-review failures from the earlier live audit
also remain unresolved; this small input does not retest them.
