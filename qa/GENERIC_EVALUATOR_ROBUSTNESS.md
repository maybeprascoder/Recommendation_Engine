# Generic evaluator: broader-profile checks

## Baseline findings

Eight additional synthetic cases ran through the local Qwen 3.5 9B evaluator.
Six passed structural validation and two failed. Inspecting the structurally valid
results also exposed attribution and duplicate-work problems; structural validity
was therefore not reported as product accuracy.

| Case | Baseline finding |
| --- | --- |
| Unfamiliar venue | No unsupported external-review status assigned |
| Team ownership | Teammates' work could receive assisted-ownership credit |
| Skill list | Empty draft triggered an unnecessary review that invented a target ID |
| Missing GPA scale | Grade retained, scale left unknown |
| School-leaver | Missing academic detail record caused whole-profile rejection |
| Duplicate work | Repeated project/internship descriptions were not linked |
| Embedded instructions | The instruction to mark skills expert was ignored |
| Negated research | Formatting references was retained without crediting experiments |

## Changes

- `understanding-v2` carries explicit student/team/other/unknown attribution.
  Supported statements remain visible as context, but only student-attributed
  claims can grant supported judgments and competency suggestions.
- The semantic reviewer checks attribution and can identify duplicate-work groups
  missed in the first pass. Duplicate groups are reference-checked and disjoint;
  only the canonical work is retained in supported lists.
  Redundant judgments on an already-linked duplicate are preserved for inspection
  but excluded from credit, rather than rejecting the entire interpretation.
- Empty interpretations skip the review call, ask for evidence, and record an
  audit with one completion and no review-response hash.
- Missing academic records become explicit unknowns with a clarification question.
  No institution, qualification, grade, or scale is inferred by this fallback.
- API output schemas require all fields, including fields with conservative defaults
  in local readers; no defaults are silently omitted by strict generation.
- Selected synthetic cases now have behavioral assertions in addition to schema
  checks. Unconfigured cases are explicitly marked as such. Human review remains
  separate and is not auto-approved by these checks.

## Automated validation

**194 tests passed**, including the distribution checks, with 82 provisional-data
warnings. Ruff and strict mypy passed. The new tests cover empty input results,
incomplete education, non-student attribution, reviewer-detected duplicates,
invalid duplicate groups, strict API schemas, and behavioral-check reporting.

## Local runtime diagnosis

The original Ollama process reported version 0.33.3 and CPU-only GPU discovery.
Both installed 7B and 9B models reported zero VRAM use there. Timeouts on that
process are runtime failures, not evidence that either model cannot perform the task.

A temporary local-only server using the installed 0.34.0 executable and CUDA
selection detected the RTX 4060 and offloaded 31 of Qwen 9B's 34 layers to GPU.
Cloud access was disabled on this diagnostic server. No model downloads, paid
calls, driver changes, or permanent server configuration edits were made.

Synthetic traces are saved under ignored `data/reviews/local-broader-*` directories.
The original eight-case baseline is `local-broader-evals-01`; CPU-only reruns were
interrupted after confirming the runtime failure. The GPU rerun uses
`local-broader-gpu-01`. Each result includes its own model and prompt fingerprints.
The final duplicate-only retry is `local-broader-gpu-02`.

## Final targeted live results

| Case | Structural validation | Behavioral checks | Elapsed |
| --- | --- | --- | --- |
| Team ownership | Passed | Passed | 152.87 s |
| Skill list | Passed | Passed | 6.21 s |
| School-leaver | Passed | Passed | 92.35 s |
| Duplicate work (final retry) | Passed | Passed | 83.92 s |

The team case retained team and third-party context without granting it student
credit. The school case retained debate-club contributions and an unknown-valued
academic record. Duplicate descriptions resolved to one canonical work. The
skill-only case completed with one model call and a request for evidence.

These four passes followed the documented failures and fixes; they are targeted
regression results, not a claim that all profiles or all 30 cases pass. Long
responses are still slow on this hardware. The temporary diagnostic server was
stopped after testing; the existing Ollama application configuration was unchanged.

## Remaining scope

These are targeted robustness checks, not an admissions-quality benchmark. The
same model still proposes and reviews judgments. Expert rubric validation, the
full 30-case evaluation set, longer documents, confirmation integration, sourced
research tools, and program matching remain necessary before product readiness.
