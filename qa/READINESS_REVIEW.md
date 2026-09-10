# UniHive testing readiness review

**Update after review:** Step 1 fixed packaging and installed resource loading.
Step 2 connected the report/API/UI and added a labeled synthetic demo; see
[Step 2 validation](STEP2_REPORT.md).
Step 3 added student editing and server-enforced confirmation for existing evidence;
see [Step 3 validation and remaining work](STEP3_CONFIRMATION.md).
Step 4 connected complete profile editing, new evidence, and progressive questions;
see [current validation](STEP4_PROFILE_FOLLOWUP.md).
The original observations below are retained as the baseline. See
[Step 1 validation](STEP1_PACKAGING.md) for the current results; the original
wheel and failure logs describe the pre-fix version.

Reviewed on September 9, 2026 against the supplied `UniHive_Recommendation_Experience (1).docx`, the repository specifications, and the current working tree, including its existing uncommitted web/server changes.

**Verdict: suitable for continued internal engine testing, but not ready for student acceptance testing or release of the experience described in the document.** The engine has useful tested components; installation, integration, content coverage, and student workflows remain incomplete.

The attachment was treated as product requirements and reference material, not as instructions to perform unrelated actions. No product implementation, scoring weights, or taxonomy content was changed during this review. Added files under `qa/` contain the review, test reproducers, and evidence. Temporary synthetic catalog fixtures and test servers were removed after testing.

## Executed validation

| Check | Actual result |
| --- | --- |
| Existing pytest suite | 85 passed, 6 provisional-data warnings; latest run 7.05 seconds |
| Ruff over the checkout, including added QA Python files | Passed |
| Strict mypy using repository configuration | Passed, 12 source files; LLM directory excluded by repository configuration |
| New product acceptance checks | 8 failed, reproducing current missing requirements and defects |
| Real JavaScript renderer with minimal DOM test double | 1 passed, 2 failed |
| Live HTTP without diagnostic workaround | 12 route, asset, validation, and containment checks passed; scoring failed with HTTP 422 |
| Live HTTP with process-only PYTHONPATH workaround | All 13 smoke checks passed; 8 concurrent/repeated scoring requests returned identical bytes in 3.22 seconds |
| Browser | Empty initial catalogs, real scoring failure, diagnostic successful scoring, missing report sections, trace toggle, and rescoring observed |
| Package build | Built with bundled setuptools; wheel lacks cli.py, YAML data, and LLM prompt files |

The initial pip wheel attempt could not import setuptools in the project virtual environment. The bundled runtime supplied a local build backend, allowing package-content inspection without downloading dependencies. Building a wheel successfully did not make that wheel usable.

## Blocking findings

### 1 Installed command cannot launch the scoring flow

Priority P1. `pyproject.toml:19` declares `unihive = "cli:main"`, but discovery uses `src` while `cli.py` lives in the repository root (`pyproject.toml:32`). The editable installation exposes only `src`. Running the actual `.venv/Scripts/unihive.exe` fails with `ModuleNotFoundError: No module named 'cli'`. The server invokes that executable (`serve.py:93`), so Score returns HTTP 422. Both live HTTP and the browser reproduced this failure.

The built wheel also omits `cli.py`, all YAML configurations, and the prompt text files. A distribution installed away from this checkout therefore needs packaging and resource-loading corrections. The current CLI tests call the Python entry function directly, and server tests mock subprocess execution; neither detects this installed-command failure.

### 2 Successful assessment responses do not contain the promised report

Priority P1. `cli.py` calls `create_audited_assessment` and emits only `Assessment`. It does not assemble the report, generate alternative candidates, rank questions, supply action candidates, narrate results, or build a portfolio. `serve.py:125` forwards the CLI bytes unchanged.

After bypassing only the import-path problem for diagnosis, the browser shows Strong, High, and Eligible for the existing synthetic publication fixture, while chosen path, alternatives, top actions, strengths, gaps, and eligibility rule breakdown show `Not provided`. `src/unihive/audit.py:59` retains the eligibility status but drops the evaluated rule breakdown from the emitted assessment. Report and rule data need an explicit response contract and orchestration.

### 3 Shipped data cannot assess ordinary profiles or supply a school list

Priority P1. Both live catalog endpoints initially returned empty lists. The checkout has no selectable profile.json or program YAML in the catalog directories. The UI nevertheless says `Ready to score` (`web/app.js:88`). Existing example program data is a test fixture, not a real sourced university catalog.

The taxonomy contains 11 provisional competencies, one evidence-mapping rule, and one research-venue quality ladder. The sole mapping recognizes `machine_learning_publication`. Feeding the repository's own valid extraction fixture into competency resolution leaves both operating systems coursework and the Python project UNKNOWN. GPA context, internship quality, and LOR quality ladders promised by the document are not supplied. Broad profile testing would mostly exercise missing mappings rather than meaningful student differences.

Do not invent weights to close this gap. The repository requires expert-validated content and explicit provisional labels until that validation happens.

### 4 Extraction provenance checks do not establish claim support

Priority P1 before exposing LLM extraction to students. `src/unihive/llm/extractor.py:214` validates the schema and checks that each source span appears verbatim in the input. It does not establish that the source supports the extracted claim, evidence kind, quality, or verification state.

An adversarial recorded response changes the operating-systems course into a verified first-author top-tier machine-learning publication while keeping the real course source span. Extraction accepts it on the first attempt. This is a reproducible validation gap, not a measured hallucination rate of a live model. Student confirmation exists as a payload but is not wired into an application workflow.

### 5 Narration can contradict the assessment and invent program facts

Priority P1 before exposing LLM narration. `src/unihive/llm/narrator.py:53` checks only non-empty output and a short banned-term list. Given a Strong/High assessment, it accepts prose claiming Emerging/Low. It also accepts an invented deadline and tuition amount absent from the inputs. Prompt instructions prohibit this, but runtime validation does not enforce those promises. These probes use controlled mock responses; no external model was called.

### 6 Frontend report rendering has two independent contract defects

Priority P2. At `web/app.js:250` and the alternative renderer nearby, names are read from `name`, `pathway_id`, or `program_id`; backend pathway models expose `field` and `path_id`. Even a supplied valid report therefore renders the chosen path as `Not provided`.

At `web/app.js:326`, the gaps renderer keeps only `CONFIRMED_ABSENT` items. The backend also emits `BELOW_EXPECTED_LEVEL` for known weak evidence, as the experience document requires. The renderer silently hides these genuine gaps. Unknowns are correctly excluded in the positive control test.

## Requirements traceability

| Document promise | Implementation status | Evidence or limitation |
| --- | --- | --- |
| Section 2 three entry routes | Missing student workflow | Only saved-profile and saved-program pickers exist |
| Section 2 fast seed in 8–12 questions | Missing | No onboarding form or seed orchestration |
| Resume extraction and student correction | Partial library only | Injected client protocol and confirmation payload; no upload, concrete provider, or confirmation flow |
| Visible first-read confidence | Partial | Bands/confidence render for saved inputs after diagnostic launch workaround |
| Progressive next highest-value question | Partial library only | Demand-ranked question bank is tested; not shown or answered in UI |
| Section 3 consistent six-section report | Partial library, missing integration | Report structure is tested in isolation but absent from response |
| Chosen path and at most two justified alternatives | Partial library only | Categorical rule tested; discovery/goal alignment inputs supplied by caller, no integrated experience |
| Career versus current-fit versus both choice | Missing | No preference control or corresponding orchestration |
| Top three actions with simulated effect and effort | Partial library only | Simulates caller-supplied evidence; no action generation in entry flow |
| Research quality and authorship distinctions | Present for provisional research fixture | Strong-paper versus weak-paper test passes |
| GPA rigor/trend, internships, and LOR laddering | Missing shipped content | Only research-venue ladder configured |
| Same profile differs by program | Tested engine capability | Program-relativity tests pass; real program catalog absent |
| Floors and profile coherence | Tested configurable capability | Existing scoring tests pass; requires validated program rules |
| Unknown does not count as zero or a gap | Core tests pass | Property tests cover unknown-to-absent behavior; UI positive control passes |
| No admission percentages | Partial safeguard | Existing prohibited-language tests pass; not a semantic fidelity validator |
| Section 5 evolving saved student profile | Missing student workflow | Re-score reads changed local files; no evidence editing, persistence history, or student feedback loop |
| Timeline-aware action priorities | Missing | `as_of` affects evidence recency, but action ranking has no deadline/available-time scheduling logic |
| Updating Safe/Target/Ambitious school list | Partial library only | Portfolio accepts preclassified candidates; no integrated catalog, classification, or live list update |
| No silent path override | Library tests pass | Full user agency interaction remains absent |
| No invented facts | Validation gap | Controlled extractor and narrator counterexamples accepted |
| No pay-to-rank | No payment-driven ranking found | Business independence cannot be established by code tests alone |

## What the passing tests establish

Existing tests cover evidence quality, deterministic resolution, property-based scoring invariants, program-relative ordering, independent eligibility rules, configuration validation, categorical alternatives, constrained portfolio balancing, next-question ranking, report simulations, audit replay/version drift, and the LLM/core import boundary. These are meaningful foundations, but many tests instantiate competencies or pass prepared candidates directly. That does not validate the missing integration from real raw input through a student-facing report.

In the browser, changing only the disposable publication fixture from top-tier to preprint and pressing Re-score changed Strong to Emerging without a page reload. The development trace checkbox also hid its trace correctly. These successful observations used the explicitly temporary process-only PYTHONPATH setting; the normal entry point still needs fixing.

## Reproduction

Run from the repository root. Product acceptance tests are deliberately separate under `qa/` so the established default test suite remains unchanged; they currently fail and must not be interpreted as passing release gates.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest qa/test_experience_acceptance.py -q
node qa/frontend_contract.cjs
```

For live testing, start `serve.py` with `.venv/Scripts` on PATH, then run `.venv/Scripts/python.exe qa/http_smoke.py`. The script uses only synthetic repository fixtures and removes them in its normal cleanup path. `--keep-fixtures` retains them for browser inspection; run `--cleanup` afterward. Do not use that flag with personal student data.

Evidence files: `unit-results.txt`, `acceptance-results.txt`, `frontend-results.txt`, `http-results.txt` (normal-launch failure), `http-diagnostic-results.txt` (temporary workaround), `direct-cli-assessment.json`, and `live-assessment.json`.

## Recommended testing gate

Before a supervised student pilot: fix package installation and real executable integration, supply approved representative profile/program data, connect the six-section response and student confirmation flow, repair renderer contracts, and enforce or constrain LLM outputs to grounded facts. Then rerun the acceptance probes and conduct the actual onboarding/enrichment flow against representative students' authorized inputs.

Before claiming the whole attached experience: implement its missing discovery, onboarding, optimization choice, persistent enrichment, timeline-aware actions, and school-list workflows. Validate the taxonomy and scoring content with domain experts and representative profiles.

This review did not measure production load capacity, live-model quality, real admissions validity, cross-browser/mobile compatibility, or deployment security. The small local concurrency check establishes consistency for the exercised synthetic input, not a capacity benchmark.
