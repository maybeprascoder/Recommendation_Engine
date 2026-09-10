# Step 3: evidence editing and explicit confirmation

Implemented and validated September 9, 2026. This extends the local review harness
using existing structured profiles; it needs no university data or API key.

## Delivered

- Evidence editor displays original claim, source, and extraction confidence.
  Students can correct claim, kind, status, quality, contribution, and date.
- Unknown, confirmed absent, and not applicable remain separate. Non-present
  states clear quality/depth; unknown evidence never becomes a weakness.
- Editing verified evidence downgrades it to self-reported, both in the preview
  and the server validator. Student confirmation cannot promote verification or
  change source text/extraction confidence.
- Explicit unchecked-by-default consent precedes scoring. Editing or changing
  selections clears consent and hides the previous result.
- `/review` captures a baseline, `/confirm` validates every original evidence ID
  exactly once through the installed CLI, and `/score` accepts only a server-owned
  confirmation ID. Direct profile/program path submissions to `/score` are rejected.
- Confirmations are separate saved snapshots under ignored `data/reviews/`.
  A second confirmation does not overwrite the first or the original profile.
  Changed source profiles and taxonomy versions require a new review.
- The report audit contains the effective profile for replay. The separate receipt
  records original profile, submitted corrections, taxonomy version, source hash,
  confirmation time, and effective profile. The report-v1 envelope stays compatible.

## Validation

| Check | Result |
| --- | --- |
| Complete pytest suite | 128 passed, 46 expected provisional-configuration warnings |
| Ruff | Passed |
| Strict mypy | Passed, 15 source files; existing LLM exclusion retained |
| Frontend regression checks | 9 passed |
| Live HTTP tests in pytest | 9 passed, using a real server and installed CLI |
| Normal catalog smoke | Review/confirm plus 14 route/contract checks passed |
| Concurrent confirmed scoring | 8 identical responses, 2.11 seconds |
| Browser | Edited claim, preview downgrade, consent gating, scoring, subsequent edit invalidation, and unknown exclusion observed |
| Distribution | Existing sdist-to-wheel-to-isolated-install tests pass; review records added to exclusion checks |

Evidence: [pytest output](step3-tests.txt), [HTTP output](step3-http.txt),
[frontend output](step3-frontend.txt). The initial full run produced 127 passes
and one timing-only Hypothesis failure: 288.95 ms initially versus 16.41 ms on retry,
exceeding its default 200 ms deadline. That correctness test now disables the
wall-clock deadline while retaining all 100 byte-equality runs and generated cases.
The final full suite passed. This change makes no performance guarantee.

## Scope and remaining readiness work

Steps 1 (packaging), 2 (report integration and display repairs), and 3 (review of
existing evidence) are implemented. The original readiness review remains a baseline.

| Original finding | Current status |
| --- | --- |
| Broken installed CLI/resources | Fixed and distribution-tested |
| Missing report integration/eligibility breakdown | Connected; alternatives/actions still need reviewed candidate inputs |
| Seed-only taxonomy and missing catalogs | Open; demo uses labeled synthetic fixtures |
| Extracted claims not semantically grounded | Human review gate implemented for structured evidence; extraction/upload not connected and semantic validation remains limited |
| Narrator factual consistency | Open; no live narrator in the scoring flow |
| Frontend field names and omitted weak gaps | Fixed and regression-tested |

Adding evidence, editing academic fields, upload/extraction, progressive questions,
live LLM providers, action/alternative input flows, and real-data calibration remain
outside this step. Confirmation is a student attestation, not proof of source support.
Local receipt files are immutable through this API, not protected against someone
with direct filesystem write access. There is no authenticated multi-user service.

Run `python serve.py --demo` with the installed CLI on PATH and follow
**Review evidence → edit → confirm → score**. Normal smoke fixtures and test servers
were removed/stopped after testing. Synthetic browser-review receipts remain under
the ignored review directory to demonstrate persistence.
