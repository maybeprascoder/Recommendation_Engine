# Local scoring review

Install the project, then start the localhost-only server from the repository root:

```bash
pip install -e .
python serve.py
```

Use `python serve.py --demo` to select the existing synthetic profile and program
without any real university data. Both selectors label those fixtures as synthetic.
Ensure the environment containing `unihive` is on PATH before starting the server.

First select **Review evidence**. Correct claims, kind, status, quality, contribution,
and date; the original claim/source and extraction confidence remain visible.
Review all items, check the consent box, then choose **Confirm and score**.
Editing afterwards invalidates consent and hides stale results. Unknown and confirmed
absent are separate states. Student corrections never gain document-verified status.

The API sequence is:

1. `POST /review` with `profile_path` and `program_path` from the catalogs.
2. `POST /confirm` with `review_id`, `confirmed: true`, and `corrections`.
   Each correction contains `evidence_id`, `raw_text`, `kind`, `state`, `quality`,
   `depth`, and `recency`. All original IDs must occur exactly once. Source and
   confidence cannot be overwritten. A changed source profile returns HTTP 409;
   reload the review. Changed taxonomy is also rejected by the CLI validator.
3. `POST /score` with `confirmation_id` only. Path-based scoring is rejected.

`POST /score` invokes `unihive --score-only --json --report` and returns its
versioned report envelope. Core scores remain under `assessment`; the six report
sections are under `report`, with the sourced `eligibility_result` beside them.
Provisional configuration and unavailable action/alternative inputs are displayed
explicitly. Plain CLI `--json` retains its previous Assessment contract.

Open `http://127.0.0.1:8000/?dev=1`. The development flag exposes the explanation trace and leaves its toggle on. Omit `?dev=1` to remove the trace panel from the page.

Profiles live under `data/profiles/`; each selectable profile must be named `profile.json`. Program configurations live under `data/programs/` as `.yaml` or `.yml` files. Both directories are scanned recursively, so scenario folders are supported.

After changing `data/bands.yaml` or a program YAML on disk, use **Re-score** to run
the same confirmed profile snapshot against current configuration. Scoring uses the
current date; the resulting audit stores that date and the inputs for exact replay.

Drafts and immutable-by-API confirmation receipts are saved under `data/reviews/`.
Receipts include original profile, corrections, effective profile, taxonomy version,
source hash, and confirmation time. These local files contain profile data; they are
excluded from Git and packages. Confirmation provenance is stored in the receipt;
the existing report envelope carries the corrected profile in its assessment audit.
Reloading the page starts a new review; saved receipts remain on disk.

All StudentProfile sections are editable in collapsible sections. Record controls
preserve nested values, booleans, numbers, and unknowns. **Add evidence** creates
student-supplied evidence; confirmed original evidence is retained and can be marked
unknown/absent rather than silently deleted. New unsaved evidence can be removed.

`POST /confirm` additionally accepts optional `profile_details` (all non-evidence
StudentProfile fields) and `additions` (the same fields as corrections, with unique
new IDs). Sources and extraction confidence are assigned by the validator for additions.

`POST /questions` takes a confirmation ID and ranks questions from the current
assessment, missing eligibility inputs, and missing goals/constraints. One question
is displayed at a time. Missing program facts stay in the report instead of becoming
student questions. Unmapped competencies disclose that answers cannot yet resolve readiness.

`POST /continue-review` takes `confirmation_id` and an optional current `question_id`.
It returns a new draft based on the confirmed snapshot. Receipts preserve the parent
confirmation ID and question context. A question that is no longer relevant returns
409. After answering, confirmation and reassessment refresh the question list.
Skipping is local to this page session and never marks an unknown as answered.

### Reviewing generic interpretations

Generate an interpretation with `unihive analyze --input resume.txt --output analysis.json`.
Select the existing profile and program, choose that JSON file in **LLM interpretation**,
then select **Review evidence**. This merges eligible claims into the selected profile
only after confirmation; the source profile file is never overwritten.

All claims are shown with original quotations, attribution, support checks and duplicate
links. Correct the statement or attribution, select confirm/exclude/uncertain, and use
the notes field for corrections to academic records or qualitative judgments. Notes and
excluded claims are retained in the receipt. A claim imports only when both its original
and confirmed attribution are student, its support check passes, it is canonical in
both extraction and support review, its statement is unchanged, and the student confirms
it. Edited statements need another support review; confirmation alone cannot override
unsupported, uncertain, duplicate or third-party status.

Imported evidence is always `SELF_REPORTED_PRESENT`, with the source quotes preserved,
low extraction confidence, null quality/depth, and
`scoring_exclusion: awaiting_approved_mapping`. Even if its category matches an existing
rule, it cannot affect competency levels or readiness, including absence states. Its
ordinary evidence controls stay read-only; edit its interpretation controls instead.
Qualitative labels and competency suggestions never become scoring weights. Academic
records retain the original grade and scale in the receipt; automatic academic profile
projection and GPA normalization are separate milestones.

`POST /review` accepts an optional `understanding` object containing the complete
`UnderstandingResult`. The server uses `unihive review-understanding --json`, passing
`{"profile": ..., "understanding": ...}` on stdin. That command revalidates exact quotes,
references, source/rubric hashes, taxonomy version and derived support lists, and returns
every claim in `claim_corrections`. `POST /confirm` accepts those corrections (claim_id,
statement, attribution, decision, notes), with each claim reviewed exactly once. The
original interpretation comes from the server-owned draft, never from the confirmation
submission. Direct CLI confirmations support the same fields in `ConfirmationRequest`.

**Download audit receipt** exports `POST /receipt` with the confirmation ID. The receipt
contains the complete interpretation (including source documents, quotes, academic
records, judgments, suggestions, model/prompt/rubric hashes and support checks), every
submitted correction, the effective profile, interpretation/profile hashes and parent
confirmation ID. Continued reviews preserve the original interpretation and previous
corrections, replacing imports instead of duplicating them. Previous receipts remain
unchanged. The assessment's profile snapshot retains each evidence scoring exclusion;
the complete interpretation remains in the separate confirmation receipt. Hashes detect
inconsistency; they do not authenticate a locally supplied analysis or independently
verify its semantic support.

This is a localhost development flow without authentication, raw document parsing,
external verification, or live LLM calls in the web server. Analysis JSON uploads stay
local. No real university data is required for the synthetic demo.
