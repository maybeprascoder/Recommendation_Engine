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

Upload/extraction and live LLM providers are not connected. Student confirmation
records a review; it does not prove that a source supports a claim. University data
and broader evidence mappings still need human validation.

See [current validation and remaining work](qa/STEP4_PROFILE_FOLLOWUP.md).

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
