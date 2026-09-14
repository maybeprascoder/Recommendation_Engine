# Semantic reliability pass

Date: 2026-09-14

This pass hardens the qualitative evidence interpreter without adding competency
nodes or changing scoring weights, admission logic, target relevance, or program
data. The reference set is synthetic, human-authored, provisional, and awaiting
expert adjudication. Live model output is evidence about model behavior and is
never treated as a training target.

## What changed

The Understanding and SupportReview prompts are now version 9. They explicitly
separate comparison or testing from impact, require a stated result for impact,
reserve measured impact for a stated measured result, and reserve adoption for
actual use. They also prevent execution verbs such as `designed`, `implemented`,
`developed`, `built`, and `created` from establishing leadership by themselves.
Publication handling preserves a named venue and explicit peer-review claim while
leaving venue quality, acceptance rate, and citation impact unknown. Absence is
scoped to the proposition stated by the source.

The semantic oracle now compares claims by exact source anchors and checks
attribution, presence, allowed category, competency routing, context, qualitative
labels, clarification questions, and explicit uncertainty. It supports narrowly
defined alternative competency interpretations: the malicious-packet parser must
retain programming and at least one supported security or networking method; both
are allowed. This avoids forcing a single taxonomy reading while still detecting a
missed demonstrated method.

Runtime instrumentation records call name, status, elapsed seconds, and prompt,
payload, and schema character counts. It does not record source contents. The
provider no longer copies a schema into the system prompt when the same schema is
already enforced by native Ollama format or JSON Schema response mode. This removes
5,586 instruction characters from Understanding and 1,284 from SupportReview per
normal two-call case while preserving provider constraints and local validation.
`UNIHIVE_LLM_MAX_TOKENS` now makes the output budget configurable; its default is
8,192. No retry loop was introduced.

## Regression coverage

The semantic reliability suite contains 77 synthetic cases:

- five domain-specific evaluation-only comparisons and four explicit impact
  boundaries;
- five execution verbs, four explicit leadership statements, and one ambiguous
  team statement;
- two publication/review statements and three narrowly scoped absence statements;
- four mixed-domain claims;
- sixteen tools at bare mention, explicit activity, and explicit independent
  execution levels, for 48 tool cases.

Every reference passes the existing two-model pipeline in recorded mode. Every
case also has an adversarial draft whose unsupported proposals are rejected by its
human-authored SupportReview reference. These checks exercise the same schemas and
confirmation path as live interpretation; they do not add keyword rules.

### Evaluation and impact

The Civil, cybersecurity, machine-learning, mechanical, and electrical comparison
cases support `evaluation=compared` and leave impact unknown. The boundary cases
keep evaluation-only, qualitative reported outcome, measured outcome, and adoption
distinct. In the focused live run, the Civil comparison remained evaluation-only,
and the measured Civil result preserved both `evaluation=compared` and
`impact=measured`.

### Ownership

Execution verbs preserve performed work and depth without automatically producing
`ownership=led`. Explicit team leadership, owned delivery, sole delivery, and a
project-lead statement can support `led`. The focused live run correctly retained
explicit leadership and represented “Our team built...” as team-attributed with no
student competency credit.

### Publication and review

The unspecified publication stayed a publication with unknown review and impact.
The explicit peer-reviewed publication supported `evaluation=externally_reviewed`
and still left impact unknown. The live model did not invent venue prestige,
acceptance rate, or citations, but it omitted the explicit `unassessed` entries and
classified the venue context as a tool instead of a concept. Those omissions remain
semantic false negatives in the final bundle.

### Absence scope

“Never used Python” creates absence only for Python experience, “no publications”
only for publication record, and “no internship experience” only for internships.
None creates competency-level absence. Confirmed absence remains excluded from
scoring until an approved mapping exists. The two focused live absence cases passed.

### Tool, method, and competency consistency

Bare ETABS, AutoCAD, ANSYS, SolidWorks, MATLAB, Arduino, Verilog, Wireshark, Nessus,
Kali Linux, TensorFlow, PyTorch, React, SQL, AWS, and Python remain context-only.
An explicit performed activity retains a demonstrated method or skill, and explicit
independent execution remains distinct from a bare mention. Demonstrated structural
methods can survive as supported suggestions with null taxonomy IDs; diagnostics
call these `unmapped_skill_needs_review`, not confirmed taxonomy absence.

### Mixed cross-domain evidence

Civil Python, cyber Python, mechanical MATLAB, and strong ML cases retain their
domain context and demonstrated work in recorded regression coverage. Programming
is not suppressed because the surrounding domain is non-CS. The focused live Civil
and cyber cases both retained programming. The cyber case also retained security
and networking methods. The Civil case added an unsupported quantitative-analysis
node, which remains a false positive. The strong ML live completion used an unknown
rubric label and was rejected as structurally invalid before SupportReview.

## Focused live validation

Model: `qwen3.5:9b` through `ollama-local`. All successful receipts used
`understanding-v9+support-review-v9` and prompt hash
`cae439c94336a18c926844f9ce65afc30bcfbb4b9b0df0722d6d833ca939a848`.
The table reports each case independently; no combined accuracy is calculated.

| Case | Structural status | Outcome classification | Finding |
| --- | --- | --- | --- |
| Civil comparison, no impact | valid | clean pass | Kept `compared`; impact remained unknown; null-ID structural method survived. |
| Civil measured impact | valid | semantic false positive; semantic false negative; reference disagreement | Evaluation and measured impact were correct. Added quantitative analysis, missed Civil domain context, chose project over activity, and used investigated rather than applied depth. |
| Explicit leadership | valid | clean pass | Preserved `ownership=led` without inventing a technical competency. |
| Ambiguous team project | valid | clean pass | Preserved team attribution, unknown ownership, and no student competency credit. |
| Unspecified-journal publication | valid | semantic false negative | Review and impact remained unknown; venue was typed as a tool and explicit venue/acceptance/citation uncertainty was omitted. |
| Explicitly peer-reviewed publication | valid | semantic false negative | Preserved external review and unknown impact; venue type and explicit uncertainty omissions remained. |
| Python absence | valid | clean pass | Scoped absence to Python and did not infer absent programming. |
| Publication absence | valid | clean pass | Scoped absence to publication record and did not infer absent research. |
| Civil Python coding | valid | semantic false positive | Retained programming and structural-load method; added unsupported quantitative analysis. |
| Cyber Python implementation | valid | clean pass | Retained programming plus supported security/networking method evidence. |
| Strong ML example | invalid | structurally invalid | Used an unknown rubric label; local contract validation rejected the draft before review. |
| Bare ETABS | valid | clean pass | Context-only; no demonstrated competency. |
| Bare Nessus | valid | clean pass | Context-only; no demonstrated competency. |
| Bare PyTorch | valid | clean pass | Context-only; no demonstrated competency. |

The final detailed bundle is
`qa/semantic-reliability-live-results.json`; raw v9 receipts and per-call timing are
under `data/reviews/semantic-reliability-live-v9-01`. The earlier v8 run is retained
for audit history but was interrupted after the prompt changed and is superseded;
it is not used for final findings.

## Runtime findings

The v9 run had no endpoint timeout or provider failure. Successful and rejected
cases took 33.28 to 69.61 seconds end-to-end, with a median of 45.92 seconds. There
were 27 completed model calls, with no retry calls. Understanding instructions were
8,807 characters plus a separately enforced 5,586-character schema; SupportReview
instructions were 6,352 characters plus a separately enforced 1,284-character
schema. The prompt-size reduction removed duplicate schema text without reducing
schema enforcement or local validation.

Latency remains high enough to monitor, and one completion exhausted its work on an
invalid label. That case is a structural-contract failure, not a runtime failure.
Future runtime work should measure model generation and validation separately before
considering architectural changes.

## Remaining failures

- The live model still over-routes quantitative analysis from a numeric result or a
  structural-load calculation when the source does not describe quantitative
  analysis as a demonstrated method.
- Publication claims need more reliable explicit uncertainty and correct venue
  context typing.
- The measured Civil example exposed activity/project and applied/investigated
  boundary disagreement. These are kept as reference disagreements rather than
  silently changing the target to match the model.
- The strong ML completion violated the rubric enum. Provider schemas and local
  validation caught it, but generation remains structurally unstable on that case.
- Null-ID structural methods show a genuine taxonomy coverage gap. They are safely
  retained and excluded from mapped scoring pending human taxonomy work.

## Readiness answers

**A. Does the system distinguish evaluation from impact reliably?** Yes for the
tested boundaries. Recorded cases cover five domains and the focused live Civil
cases correctly separated comparison from result. Broader live sampling is still
needed before treating this as universal model reliability.

**B. Does bare tool/context remain non-scoreable?** Yes. All 16 recorded bare-tool
cases and the live ETABS, Nessus, and PyTorch cases remained context-only.

**C. Can genuine demonstrated skills survive with null taxonomy IDs?** Yes. Null-ID
methods survive SupportReview and are reported as needing mapping review rather than
as absent or unsupported.

**D. Can genuine cross-domain programming still be recognized?** Yes. Civil Python,
cyber Python, and mechanical MATLAB regressions retain programming; the two focused
live Python cases also retained it.

**E. Is ownership inflation sufficiently controlled?** Yes for the tested
non-scoring semantic boundary. Execution verbs do not imply leadership, explicit
leadership survives, and ambiguous team work does not receive student credit.

**F. Is publication/review hallucination sufficiently controlled?** The dangerous
positive inferences are controlled in these tests: unspecified publication did not
become peer-reviewed, prestigious, cited, or impactful. Completeness is not finished
because live output omitted explicit uncertainty and mistyped the venue context.

**G. Is explicit absence scoped safely?** Yes for Python, publication, and internship
boundaries. No competency-wide absence is inferred.

**H. Are remaining failures mostly semantic, taxonomy-related, or runtime-related?**
They are mostly semantic and representation failures, plus one structural-contract
failure and a visible taxonomy coverage gap. The final v9 set had no runtime failure.

**I. Is the semantic layer now stable enough for a SMALL competency taxonomy
expansion?** Yes, if the expansion is provisional, human-reviewed, and initially
non-scoring. Structural methods retained with null IDs provide concrete candidates.
The quantitative-analysis false positives should block automatic mapping, not a
small reviewed addition.

**J. Is it stable enough to begin building human-reviewed training data?** Yes. The
export path already separates provisional human annotations from model output and
contains qualitative fields only. Expert adjudication must occur before references
become gold labels, and live predictions must never be promoted automatically.

## Validation

- Pytest: 692 passed.
- Ruff: passed after the final formatting correction.
- Strict mypy: passed for 19 source files.
- Frontend contract: 14 passed.
- `git diff --check`: passed; Git reported existing LF-to-CRLF conversion warnings
  only.
