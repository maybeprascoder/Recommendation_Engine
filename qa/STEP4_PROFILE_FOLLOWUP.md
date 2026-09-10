# Step 4: complete profile editing and progressive follow-up

All StudentProfile sections can now be edited, including nested academic/test/work
records, goals, constraints, citizenship and residency. Blank GPA remains unknown;
no automatic GPA conversion is performed. Existing evidence sources are preserved;
new evidence is student-supplied and cannot gain verified status.

After scoring, the interface displays one ranked question at a time. Updating that
information starts a review from the latest confirmed snapshot, opens the relevant
section, and requires confirmation before reassessing. Receipts retain parent
confirmation and question context. Resolved questions disappear; skipping leaves
the profile unchanged. Missing university facts are not presented as student questions.

Validation on September 9, 2026:

- Full pytest suite: **137 passed**, 82 provisional-configuration warnings.
- Ruff passed; strict mypy passed for 16 source files.
- Frontend contracts: **12 passed**, covering typed profile values, evidence additions,
  confirmation invalidation, sequential questions, skipping, and report rendering.
- Live HTTP integration: **10 passed**, including changed GPA/new evidence followed
  by an answered question, immutable earlier snapshots, saved lineage, refreshed
  questions, stale-question rejection, and assessment replay.
- Distribution tests exercise the installed wheel and editable console executable.
- Browser verification: changed GPA, confirmed/scored, opened the constraints
  follow-up, saved an answer, reassessed, and observed the resolved question disappear.

Captured full output: [pytest](step4-tests.txt), [frontend](step4-frontend.txt).

Steps 1–4 now cover packaging, report integration/display repairs, evidence
confirmation, complete profile editing, and progressive questions. Remaining:
document extraction and live LLM integration/grounding; broader reviewed taxonomy
and evidence mappings; reviewed alternative/action inputs; real university catalogs
and calibration. This validates the synthetic workflow, not admissions accuracy.

Profile-record editing intentionally does not create competency mappings. New claims
with an unsupported kind stay unassessed. Student confirmation records an attestation,
not proof that the cited text supports a claim. Receipts remain local under ignored
`data/reviews/`; refresh starts a new page session.
