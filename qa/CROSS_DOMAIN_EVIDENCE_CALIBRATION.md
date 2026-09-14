# Cross-domain student evidence calibration

This is an audit and calibration task on the existing architecture. Synthetic
references, mocked pipeline checks and live local-model observations are reported
separately. Passing a mocked check is not evidence of semantic model accuracy.

## 1. Current architecture audit

The pipeline remains documents → UnderstandingDraft → qualitative judgments →
SupportReview → student confirmation → versioned mapping → Evidence → deterministic
evaluation → competencies. No new evaluator, validator agent, lookup or target-program
system was added.

- **UnderstandingDraft:** claims, attribution, category, quotations, four qualitative
  dimensions, academic records, competency suggestions, questions and unassessed notes.
  Domain/tool/method context can be retained in claim wording and observed skills;
  it has no dedicated domain-context structure in the production schema. The golden
  fixture keeps those annotation concepts separately for future dataset work.
- **SupportReview:** one bounded second pass, checking every target and duplicate
  groups. It validates source support, not real-world truth. Exact citation and
  reference checks are deterministic; semantic verdicts remain fallible model outputs.
- **Confirmation and projection:** supported, unchanged, canonical student claims
  become self-reported Evidence. The generic record remains excluded. A mapping also
  requires supported, unchanged judgments and a supported same-claim competency ID.
  Student edits cannot override a rejected interpretation.
- **Mapping/routing:** 24 provisional rules, four categories, only programming and
  machine learning. There is no nearest-node fallback. Unknown IDs are rejected;
  supported skills with null IDs can survive in the receipt. Highest priority wins
  per claim/competency. A mapped item is restricted to its selected evidence rule.
- **State handling:** self-reported and verified-present factors remain 0.8 and 1.0.
  Unknown competencies remain unassessed, not zero or confirmed absent. Existing
  explicit CONFIRMED_ABSENT inputs stay distinct and grant no positive contribution.
  A limitation remains: SourcedClaim has no typed absence field. An interpreted
  statement of absence stays in source text; confirmation does not project it into
  typed CONFIRMED_ABSENT competency evidence. Tests distinguish this limitation from
  the existing deterministic state behavior instead of pretending it is implemented.
- **Combination:** existing sorting, diminishing-return prefix and explanation traces
  are preserved. A test exposed an unbounded constant tail; section 11 describes the
  narrow configurable correction.

**Bias:** the scoring catalog favors software/ML through coverage. The code does not
force other disciplines into them. A model can nevertheless propose and incorrectly
approve an unrelated existing competency; the live BERT run demonstrates this risk.

## 2. Domains tested

The core suite has exactly 25 cases: software 4, ML/data science 4, cybersecurity 4,
civil/structural 4, electrical/embedded 3, mechanical 3, interdisciplinary/research/
teaching 3. Thus 17 of 25 core cases are outside software and ML.

There are also 29 focused probes: the ten requested vague/adversarial statements,
14 standalone tool cases, and five method/routing/ownership/mapping probes. Tools
include AutoCAD, ETABS, ANSYS, SolidWorks, MATLAB, Arduino, Verilog, Wireshark, Nessus,
Kali Linux, TensorFlow, PyTorch, React and SQL. AWS, BERT and Python also appear.

## 3. Golden fixture summary

`tests/fixtures/understanding/cross_domain_golden.json` contains complete reference
drafts, support-review outputs and supported-ID oracles, plus separate adversarial
drafts and expected rejection/uncertainty verdicts. Every target has exact source
citations. Every case is marked as a **provisional synthetic reference**, with no
named human validation. These are not adjudicated admissions-quality gold labels.

| Domain | Case IDs | Main progression or distinction |
| --- | --- | --- |
| Software | software-tool, software-basic, software-api-design, software-deep-duplicate | React/AWS names → tutorial implementation → API/queue design → measured service with duplicate internship description |
| ML/data | ml-tool, ml-basic, ml-compared, ml-deep | Framework names → classifier training → pipeline comparison/SQL analysis → measured BERT evaluation |
| Cybersecurity | cyber-tool, cyber-basic, cyber-investigation, cyber-deep | Wireshark name → packet analysis → individual team investigation → detection utility, replay and measurement |
| Civil | civil-tool, civil-basic, civil-designed, civil-deep | ETABS/AutoCAD names → modeling → member/load design → compared alternatives and estimated material savings |
| Electrical | electrical-tool, electrical-basic, electrical-deep | Arduino/Verilog names → sensor integration → control design, error characterization and filter comparison |
| Mechanical | mechanical-tool, mechanical-model, mechanical-deep | SolidWorks/ANSYS names → CAD/interference checking → design variants, simulation, MATLAB analysis and estimated mass reduction |
| Interdisciplinary | neutral-teaching, neutral-civil-python, neutral-research-absence | Teaching evaluation; explicit Python plus structural work; qualitative interview research, publication and stated programming/ML absence |

The 54 recorded scenarios pass their reference oracles. Eight core cases have at
least one production scoring projection; 15 have supported coverage gaps, sometimes
alongside a valid programming/ML projection. An empty contribution dictionary is
reported as **null/not assessed**, not numerical zero. See
`cross-domain-recorded-results.json` for the per-case gap ledger and arithmetic.

## 4. Weak → medium → strong progression

The same four dimensions express all six domain progressions. No additional rubric
dimension or numeric LLM output was needed. Tool-only evidence has unknown depth;
concrete implementation/modeling can be applied; described design or investigation
can be deeper; explicit alternatives and measurements support compared/measured.

| Domain | Production behavior | Isolated mapping arithmetic probe |
| --- | --- | --- |
| Software | Not assessed → programming 0.64 → 1.6 → 2.4 | Same progression |
| ML | Not assessed → ML 0.64 → 1.6 → 2.4 | Same progression |
| Cybersecurity | No networking/security scoring route; explicit Python in the strong case maps to programming | Not assessed → 0.64 → 1.6 → 2.4 |
| Civil | Supported work preserved; no structural nodes/routes | Not assessed → 0.64 → 1.6 → 2.4 |
| Mechanical | Supported work preserved; no mechanical routes | Not assessed → 0.64 → 2.4 |
| Electrical | Supported work preserved; no embedded/hardware routes | Not assessed → 0.64 → 2.4 |

These numbers are internal evidence contributions under fixed self-report/undated
factors, never final student scores. The non-covered-domain arithmetic probes use
an explicitly test-only synthetic target, reusing the existing mapping conditions,
priorities and coefficients. They do **not** add production taxonomy nodes or claim
that those domains currently score. Unknown first steps are excluded from arithmetic.

## 5. Hallucination findings

The initial live civil smoke run on local `qwen3.5:9b` passed structural checks but
incorrectly approved ownership=led from action verbs alone. Its reviewer also called
a source-supported structural skill uncertain because competency_id was null.
Both were real model errors, not fixture plumbing errors.

The original blanket "no outside knowledge" instruction was narrowed to allow
semantic terminology recognition while keeping supplied documents as the only source
of student accomplishments. Prompt v5 explicitly separates personal action from
leadership and catalog absence from semantic uncertainty. It also names misleading
tool-to-domain and domain-to-competency shortcuts. This does not guarantee compliance.

The revised live sample covers all seven core domain groups plus two tool-only
probes. Full results and the final manual interpretation appear in the live appendix.
Schema/provenance failures and reference-label disagreements are distinguished from
clear invented accomplishments. The automated oracle is deliberately narrow; it
cannot certify every sentence, publication fact or disciplinary judgment.

The neutral research receipt exposed a clear invented review status: the model and
SupportReview both inferred externally_reviewed from publication in an unspecified
journal. The original oracle collapsed judgments across claims and missed that label
when a later research claim had a valid compared label. The oracle now retains every
supported label and has a regression test for this masking failure.

## 6. SupportReview rejection behavior

All 54 scenarios include adversarial proposals: unsupported depth, ownership,
evaluation or impact upgrades and false programming/ML suggestions where inappropriate.
The team probe includes an uncertain ownership verdict. Tests confirm that rejected
or uncertain IDs cannot activate scoring and produce clarification questions.
Reference tool-only cases retain unknown dimensions and no demonstrated competencies.

The live ETABS and Nessus receipts kept depth/ownership/impact unknown and granted
no scored competency, but stored bare tool usage as supported null-ID skills. This is
a tool/context representation mismatch against the reference contract, not evidence
that the model invented high expertise. The oracle now flags it rather than treating
the resulting "taxonomy gap" as a reason to add a tool-specific competency.
The Nessus activity record also omitted a clarification question. The existing
deterministic fallback now covers coursework/activity/other records and asks a
domain-neutral question about personal methods and evaluation. A recorded regression
tests this fix; no new model pass or automatic semantic approval was added.

These rejection tests use recorded review responses. They establish correct gating,
not that a live model will always reject the proposals. Live tests show the same model
can endorse its own over-interpretation. Deterministic code does not silently promote
null-ID suggestions or override a model verdict to manufacture a green result.

## 7. False-positive competency mappings

No false routing occurs in the recorded suite with the expected review verdicts.
Specific regressions cover ETABS→programming, MATLAB/ANSYS→ML, OpenAI API→ML,
SQL analysis→database engineering and interview coding→software. An OpenAI API app
may support application programming without supporting ML model engineering.

The revised live BERT case incorrectly received additional programming and statistics
suggestions under the reference policy: no code-writing or separate statistical
method was stated. SupportReview accepted them. Programming then received an actual
2.4 contribution; statistics had no qualitative route. This is a semantic false
positive that the mapping gate cannot identify once its supported-ID inputs are wrong.
Any additional discovered live false positives are listed in the appendix/JSON ledger.

## 8. False-negative competency mappings

There are three different mechanisms; they must not be conflated:

1. A demonstrated skill has no catalog node: legitimate coverage limitation.
2. A known node (networking, security, quantitative_analysis) lacks a qualitative
   scoring route: configuration coverage limitation.
3. A model omits or rejects supported skill evidence: semantic false negative.

The initial civil reviewer rejected an uncatalogued structural skill solely for its
null ID. The revised cybersecurity packet-analysis case omitted the expected supported
networking competency. The revised BERT case failed to retain the expected uncatalogued
NLP context as a supported skill. Live findings are observations against provisional
reference labels and require human adjudication before use as training corrections.

## 9. Missing taxonomy coverage

Recorded gaps include structural modeling/member design/load analysis; CAD and
mechanical assembly design; simulation comparison; sensor integration, characterization
and digital/embedded control; qualitative research analysis; teaching design/evaluation;
NLP classification; and SQL data querying. No nearest unrelated competency is substituted.

Prioritize expert definitions for structural analysis/design, mechanical design and
simulation, embedded/digital systems and sensing, and qualitative research/teaching.
For cybersecurity, review the existing networking/security definitions and missing
routes before inventing many new nodes; consider detection/vulnerability workflows
only where evidence supports a meaningful distinction. Quantitative analysis already
exists and needs routing calibration. No giant taxonomy was added.

## 10. Monotonicity results

Six isolated qualitative-to-mapping progressions are non-decreasing. Software and ML
also pass progression through the actual production routes. Unmapped civil/cyber/
mechanical/electrical competencies are explicitly not assessed; their lack of a score
is not passed off as an equal-zero monotonicity success.

The tests hold verification, recency and numeric configuration fixed. These are
configuration checks using reference qualitative labels, not a claim that a live
model reliably orders all student evidence. The same-label arithmetic is invariant
to disciplinary vocabulary; semantic recognition and coverage are separate concerns.

## 11. Duplicate and diminishing-return results

The repeated campus service under project and internship descriptions produces one
mapped item. Existing duplicate handling and repeat confirmation are preserved.
Independent strong evidence still accumulates, with decreasing increments.

An actual baseline failure was found: the original constant 0.05 tail let 60
independent basic activities contribute **2.688**, exceeding one deeply evaluated
activity at **2.4**. This was unlimited quantity accumulation, not duplicate inflation.

The correction adds `tail_mode` to the existing combination configuration. The checked-in
mode is geometric: after the unchanged 1.0, 0.25, 0.1 prefix, the first tail remains
0.05 and subsequent factors extend the existing ratio 0.05/0.1. No new coefficient was
invented. Legacy configurations default to constant mode; invalid non-decreasing
geometric tails fail validation. The YAML content hash changes, preserving versioning.

With the configured geometric tail, arbitrarily many equally basic self-reported,
undated items approach **0.928**, below one deep item. Tests exercise 60 and 1,000
distinct items. Two, three and four independent strong items still add value.
This is provisional calibration: under the same self-report/undated factors, the
deep-item total approaches 3.48, interacting with the existing level thresholds.
That ceiling deserves outcome/expert calibration; no thresholds were silently changed.

## 12. Mapping limitations discovered

The current three alternatives remain deliberately coarse:

- Designed + measured without comparison stays in the middle tier.
- Designed + validation/testing uses evaluation=described; `validated` is not an
  allowed rubric label. It stays in the middle tier.
- Investigated + compared, without measured impact, stays in the middle tier.
- Concrete implementation uses applied; method design uses designed. A tool name
  alone must not establish either. Borderline cases need adjudicated exemplars.
- Research investigation and engineering design share a depth factor despite
  different activities. Testing, formal comparison and measurement remain distinct
  labels even when their current numeric outputs are equal.
- Reported qualitative outcomes, measured outcomes and adoption cannot always coexist
  in the single impact label. A model choosing adopted instead of measured may lose
  eligibility for the stronger rule. This is a representational/calibration risk,
  not a reason to assign arbitrary new bonuses in this task.
- Coursework and activity have rubric guidance but no shipped qualitative mappings;
  teaching is therefore limited by both node coverage and category routing.
- Ownership labels currently do not alter numeric quality/depth. Unsupported leadership
  is still a product error even when it does not increase this mapping's contribution.

Tests explicitly expose middle-tier plateaus rather than adding arbitrary distinctions.
The mapping mechanism is domain-independent; the shipped content is not broad enough
for cross-disciplinary scoring yet.

## 13. Instruction-tuning dataset readiness

Every fixture retains source text, complete expected claims/category/attribution,
all four dimensions, unknown fields, supported skills, citations, contextual concepts,
recognized tools, actual methods, expected support review and adversarial rejections.
The context sidecar is annotation metadata, not a silently added production schema.

The runner exports two reference records per scenario: source→UnderstandingDraft and
source+adversarial draft→SupportReview. For all 54 scenarios that is 108 JSONL records.
No final numeric scores, mapping priorities, numeric quality/depth factors, target
relevance, fit or admission labels are included. Source measurements such as 11% material
reduction remain legitimate source facts. Numeric calibration diagnostics are saved
separately and excluded by tests from the training export.

Structurally ready for later curation; **not ready for unreviewed fine-tuning**. All
references are synthetic and provisional, some dimensions admit reasonable alternatives,
and the current taxonomy definitions are sparse. Preserve case/progression groups in
future splits to prevent near-duplicate leakage. Live outputs must not become targets
without human review. No training run or model download occurred.

## 14. Intentionally unfinished work

No university/program ingestion, target relevance, admissions probability, portfolio,
institution/publication APIs, giant taxonomy, multi-agent framework or numeric LLM
scoring was built. The existing program-data gate was untouched. No real student data
was sent to an external service; live probes used the already-installed local model.

Open work includes semantic model reliability, expert reference adjudication,
coverage definitions, explicit absence projection, simultaneous impact facets,
category routing and empirical calibration of the revised diminishing-return tail.
The existing draft/reviewer contracts and four dimensions were preserved.

## 15. Recommended next architectural step

Stay within the current architecture. First adjudicate the failed live cases and
define clearer evidence requirements for the existing competency nodes. Validate
ownership, null-ID support and tool/method separation on a held-out set. Calibrate the
middle-tier plateaus, impact representation, quantity ceiling and typed absence handling
before broadly expanding scoring routes. Then add a small expert-defined set of the
identified domain nodes and reuse the same mapping/support/confirmation machinery.

Do not solve review errors by automatically accepting null-ID suggestions, by keyword
blacklists that discard valid cross-domain programming, or by adding another judge agent.

## Reproduction and task changes

Run with the repository virtual environment:

```text
python -m qa.cross_domain_evidence --all --include-probes --output data/reviews/new-cross-domain-run
python -m pytest -q --disable-warnings --tb=short --basetemp=.pytest_tmp_new_cross_domain_run
python -m ruff check .
python -m mypy --strict src/unihive
node qa/frontend_contract.cjs
git diff --check
```

Use a fresh output directory. `--mode live --case ID` uses the explicitly configured
provider through the existing LLM adapter; recorded is the default and makes no model
calls. Review complete receipts, not only the automated oracle's summary.

This task adds the golden fixture, `qa/cross_domain_evidence.py`,
`tests/test_cross_domain_evidence.py`, this report and `qa/cross-domain-*` result files.
It changes the two existing LLM prompts and their audit version, the existing
combination configuration/schema, and the existing evidence/competency combination
code. Earlier bridge work in the working tree is preserved. No earlier tests were
weakened or removed.

## Live appendix: targeted observations, not an accuracy certification

The initial civil smoke used prompt v4. The nine-case pass used prompt v5 with local
`qwen3.5:9b`, a 16,384-token context and 180-second request timeout. Five cases returned
structurally valid results; three failed schema/provenance validation; one timed out.
All five valid receipts have a mismatch against the final narrow reference oracle.
The mismatches differ in severity and should not be combined into a hallucination rate.
This was a targeted subset, not live execution of all 25 core cases or all 54 scenarios.

| Case | Structural result | Observed finding | Seconds |
| --- | --- | --- | ---: |
| software-api-design | Rejected | Duplicate judgment for a claim/dimension; failed closed before scoring | 47.43 |
| ml-deep | Passed | Unsupported led; programming inferred from deployment; statistics inferred from F1; expected uncatalogued NLP skill omitted | 66.03 |
| cyber-basic | Passed | Packet-analysis activity retained with applied depth; expected networking suggestion omitted | 42.31 |
| civil-deep | Rejected | Non-exact citation; failed closed before scoring | 26.88 |
| electrical-deep | Timed out | Runtime outcome; no semantic conclusion can be drawn | 180.05 |
| mechanical-deep | Rejected | Non-exact citation; failed closed before scoring | 37.80 |
| neutral-research-absence | Passed | Unsupported external-review label; supported research skill omitted; absence retained in a separate claim | 98.15 |
| tool-etabs | Passed | No high labels or scores; bare usage stored as a supported null-ID skill | 44.92 |
| tool-nessus | Passed | No high labels or scores; bare usage stored as a supported null-ID skill; missing clarification subsequently covered by fallback regression | 41.24 |

In the neutral research case, impact=reported for an explicitly published output
and splitting publication/research/absence into three claims are reference-label and
granularity disagreements, not established hallucinations. In contrast, inferring
external review from the journal mention is clearly unsupported. Similarly, the NLP
source wording is preserved even though the expected separate skill suggestion is
missing. These distinctions require adjudication before collecting training targets.

`cross-domain-live-results.json` contains the original v4 receipt, all available v5
receipts, original oracle findings and corrected oracle findings. It preserves model,
prompt, rubric and source provenance. Rechecking receipts did not rerun the model.
`cross-domain-live-smoke.txt` and `cross-domain-live-v5.txt` retain raw run summaries.
The electrical timeout remains recorded; it was not replaced by a favorable retry.

## Explicit answers A–F

**A. Can the current system interpret cross-domain evidence without significant
hallucination?** Not reliably established. It can represent grounded cross-domain
evidence, and the deterministic checks work, but live ownership/external-review
overclaims and missed skills prevent a claim of cross-domain reliability.

**B. Does the taxonomy cause force-fitting into programming/ML?** There is no
deterministic fallback, but the narrow catalog creates coverage pressure. The live
model did produce unsupported existing-node suggestions, and SupportReview accepted
them. The bridge is only as reliable as those semantic inputs.

**C. What needs expansion next?** Small, expert-defined structural analysis/design,
mechanical design/simulation, embedded/digital systems/sensing, qualitative research
and teaching coverage. First clarify existing networking/security/quantitative-analysis
nodes and their missing routes. NLP and data-querying distinctions also need review.

**D. Is the mapping system general enough?** The machinery and four dimensions are
general enough for the tested progressions. The present mapping content, categories
and coarse quality alternatives are not sufficient for broad disciplinary scoring.

**E. What should be calibrated before expansion?** Semantic review reliability,
ownership, null-ID support, tool/context distinction, source-versus-venue review,
middle-tier plateaus, single-label impact, typed absence and the quantity ceiling.
The unlimited constant-tail problem was fixed narrowly and remains provisional.

**F. Are fixtures ready for later instruction-tuning data?** Structurally yes:
grounded drafts/reviews, context annotations, unknowns, adversarial targets and
score-free export are present. They are synthetic, provisional and not ready for
unreviewed training. Expert adjudication and held-out evaluation must come first.

## Final validation

- Full pytest: **400 passed, 4068 warnings in 258.37s (4:18)**; no failures or skips.
  Command: `.venv/Scripts/python.exe -m pytest -q --disable-warnings --tb=short --basetemp=.pytest_tmp_cross_domain_final_02`.
  Warnings include repeated provisional-configuration disclosures. A repository-local
  temporary directory avoids the Windows default temporary-directory permission issue.
- Ruff: **all checks passed** over the repository.
- Strict mypy: **no issues in 19 configured deterministic source files**.
- Existing frontend contract: **12 passed, 0 failed**.
- `git diff --check`: **clean**.

Logs: `cross-domain-pytest.txt`, `cross-domain-ruff.txt`,
`cross-domain-mypy.txt`, `cross-domain-frontend.txt`. Recorded fixtures and live runs
are distinct from these automated checks. The nine-case live run intentionally returns
a failing status for the observed mismatches; it is not reported as green.

Work stops at this calibration deliverable. No next feature was started.
