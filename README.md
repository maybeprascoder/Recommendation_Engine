# UniHive engine

A deterministic admissions assessment engine under development. The bundled
taxonomy and scoring configuration are provisional. The local web page is a
review harness; the complete student experience is not implemented yet.

## Install and test

Use Python 3.11 or later. From this directory on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
```

On macOS/Linux use `.venv/bin/python` and `.venv/bin/unihive` instead of the
Windows `Scripts` paths. Install before testing: the editable install maps the
configuration package to the authoritative `data/` directory.

Run the existing synthetic example without an API key:

```powershell
.\.venv\Scripts\unihive.exe --score-only --profile tests/fixtures/cli/profile.json --program tests/fixtures/cli/program.yaml --as-of 2026-01-01 --json
```

Pass `--as-of` for comparable manual runs. To replay a saved assessment JSON:

```powershell
.\.venv\Scripts\unihive.exe replay --audit assessment.json --json
```

Screen a directory of sourced program records with the multi-program command:

```powershell
.\.venv\Scripts\unihive.exe recommend --profile profile.json --program-dir data/programs --as-of 2026-09-11
```

The command assesses only records allowed by `data/program_data_policy.yaml`.
Provisional, unreviewed, stale, or future-dated records are returned with explicit
hold reasons and no assessment. The checked-in policy is itself provisional, so
it cannot silently enable recommendations. Developers may add
`--include-blocked-diagnostics` to exercise the deterministic path; those results
remain marked `diagnostic_only` and `recommendation_ready` remains false.

## Local scoring review

The server invokes the installed `unihive` command, so put the virtual
environment's executable directory on PATH before starting it:

```powershell
$env:PATH = (Join-Path $PWD '.venv\Scripts') + ';' + $env:PATH
.\.venv\Scripts\python.exe serve.py
```

Without university data, use the existing labeled synthetic fixtures:

```powershell
.\.venv\Scripts\python.exe serve.py --demo
```

Demo mode reads only `tests/fixtures/cli/`. It does not populate or modify your
real profile/program catalogs, and its results are not university recommendations.

Open `http://127.0.0.1:8000/?dev=1`. Selectable inputs must be supplied under
`data/profiles/` as `profile.json` and under `data/programs/` as YAML. Those
catalogs are initially empty. The fixtures in `tests/fixtures/cli/` are synthetic
test data, not verified university recommendations.

Choose **Review evidence**, edit each claim and its status, then check the explicit
confirmation box and choose **Confirm and score**. Sources and extraction confidence
remain unchanged. Editing verified evidence makes it self-reported. Every later edit
clears consent and hides the previous assessment until you confirm again.

The local server stores separate draft and confirmation records in `data/reviews/`,
excluded from Git and distributions. Original profiles are never overwritten.
The API now requires `POST /review` with profile/program paths, `POST /confirm` with
the returned review ID and corrections, then `POST /score` with a confirmation ID.
Direct path-based HTTP scoring is rejected. The low-level CLI still accepts ordinary
structured profiles for deterministic tests and developer use.

Expand the profile sections to edit academic history, GPA, courses, skills, projects,
research, work, goals, constraints, tests, citizenship, and residency. **Add evidence**
records a new student-supplied claim with low extraction confidence; it cannot grant
verified status. Structured profile records do not automatically become competency evidence.

After scoring, **What would help next** shows one ranked question. Choose **Update
this information**, edit the relevant section, then confirm and score again. The new
review starts from your latest confirmed profile and retains previous changes. **Not
now** skips a question for this page session without changing your profile.

Web upload/extraction is not connected. The separate `analyze` CLI below now has
a live model adapter and proposed qualitative evidence review. Student confirmation
records a review; it does not prove that a source supports a claim. University data
and broader evidence mappings still need human validation.

See [current validation and remaining work](qa/STEP4_PROFILE_FOLLOWUP.md).

## Generic evidence evaluator (first milestone)

`analyze` reads arbitrary UTF-8 text documents, proposes source-linked claims,
preserves academic records and original grading scales, applies a provisional
qualitative rubric, and runs a separate model support check. Projects, work,
unpublished research, publications, coursework, and nontechnical activities are
supported categories. Unfamiliar skills remain visible even without a taxonomy ID.
This is an interpretation draft requiring review, not an admissions score.

Use an installed local Ollama model without paid API calls. These variables apply
to the current PowerShell session only; no account or API key is required:

```powershell
$env:UNIHIVE_LLM_PROVIDER = 'ollama'
$env:UNIHIVE_LLM_BASE_URL = 'http://127.0.0.1:11434'
$env:UNIHIVE_LLM_MODEL = 'qwen3.5:9b'
$env:UNIHIVE_LLM_CONTEXT = '16384'
$env:UNIHIVE_LLM_TIMEOUT = '180'
.\.venv\Scripts\unihive.exe analyze --input tests/fixtures/understanding/student.txt --output data/reviews/example-understanding.json
```

Choose a model you have installed. Local mode rejects cloud tags and remote
endpoints and never switches to a paid model on failure. It uses the native
Ollama API to set context size, disable thinking, and request schema-shaped JSON.
Model quality and latency must be evaluated; fitting the weights into memory
does not guarantee sufficient context memory or reliable judgments.

On Windows, the same local configuration is available through
`./run-local-analysis.ps1 -InputPath student.txt -OutputPath data/reviews/new.json`.

The replaceable adapter also supports explicitly configured OpenAI-compatible
servers with `UNIHIVE_LLM_PROVIDER` unset, a base URL ending in `/v1`, and optional
`UNIHIVE_LLM_API_KEY`. No credentials are stored in output. An OpenAI key is never
automatically sent to another host. `UNIHIVE_LLM_OUTPUT_MODE` supports `json_schema`,
`json_object`, or `prompt` for servers with different capabilities; local validation
always remains strict. No automatic mode downgrade or provider fallback occurs.

Repeat `--input` for supporting text files. IDs follow input order (`document-1`,
`document-2`). PDF/OCR and the web review connection are future milestones.
`--output` creates a new file exclusively; it never overwrites a document or report.
Reports contain the supplied text; keep personal outputs under ignored `data/reviews/`.

The result keeps all proposed statements in `draft`, including rejected proposals,
with `support_review` verdicts and explicit supported-ID lists. Consumers must use
those lists, not treat the entire draft as approved evidence. Unknown judgments
and children of rejected claims are excluded from supported judgments. Model
support means consistency with the source, not independent factual verification.
No semantic interpretation is inserted into deterministic scoring in this milestone.
If the model omits a rubric dimension, the engine adds an explicitly labeled
unknown judgment with a rationale stating that the model did not assess it.

`understanding-v2` additionally records whether a claim describes the student,
their team, another person, or unclear responsibility. Only supported claims
attributed to the student can grant supported judgments or competency suggestions.
The reviewer can also identify duplicate-work groups missed by extraction; those
groups retain the source statements but exclude duplicate items from supported
lists. These are model judgments requiring review, not verified facts.

When a school-status claim has no extracted academic record, the engine supplies
an all-unknown record and asks for clarification. It never invents a qualification
or GPA. If there are no claims to check (for example, an unsupported keyword list),
the second model call is skipped and the response asks for supporting evidence.
The audit then contains one completion and a null review-response hash.

For repeatable offline plumbing tests, pass `--recorded-responses` containing
`{"draft": <UnderstandingDraft>, "review": <SupportReview>}`. These outputs are
explicitly marked `recorded-offline`; they do not establish live model quality.

Thirty synthetic evaluation cases and human-review expectations are in
`tests/fixtures/understanding/cases.json`. Run a selected subset against your model:

```powershell
.\.venv\Scripts\python.exe qa/run_evidence_evals.py --case unpublished-research --case tutorial-project --output data/reviews/eval-run-1
```

Use a new output directory each time. `--all` explicitly selects all cases.
The runner retains synthetic responses and reports schema/provenance validation
separately from human review. Validation passing is not semantic accuracy passing.
For selected adversarial cases it also runs explicit behavioral checks. Cases
without these checks are marked `not_configured`, never automatically passed.
These narrow checks do not replace expert evaluation of the complete explanation.

The rubric is a versioned, unvalidated draft, not admissions expertise. One model
reviewing its own draft can repeat its mistakes. Remaining work includes human
evaluation, broader live cases, clarification/confirmation integration, external
source retrieval, reviewed competency mapping, and sourced program comparison.

Protocol references: [Ollama native chat](https://docs.ollama.com/api/chat),
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs), and
[compatible API](https://docs.ollama.com/api/openai-compatibility).

The web API returns a versioned envelope with `assessment`, `eligibility_result`,
`report`, `provisional`, and `limitations`. The six-section report shows evidence,
strengths, known gaps, the selected path, actions, and unresolved fields.
Alternatives and actions remain explicitly unassessed until reviewed candidate
inputs are connected; the engine does not invent them.

Use `--json --report` with the scoring CLI for the same envelope. The existing
`--json` output remains an unchanged Assessment object. `replay --audit FILE
--json --report` accepts either format and reproduces the report from its saved
assessment inputs; when the input is a report envelope it verifies that report
as well. `response_version` is currently `report-v1`.

## Package resources

`cli.py` is installed as the console entry module. Versioned YAML and JSON
schemas from `data/` are installed as `unihive._data`, and LLM prompt files are
included under `unihive.llm`. Editable installs read the same source files used
for local tuning. Wheels include a snapshot of those files and can score from
outside the source checkout. Profile and program catalogs are external inputs;
they are excluded from distribution artifacts.

`tests/test_packaging.py` builds a source distribution, builds a wheel from it,
installs that wheel into a disposable environment, and runs its real executable
from a separate directory. It reuses installed test dependencies without
network access. Build dependencies are included in the `dev` extra.
