# Qwen 3.5 9B provisional-data diagnostics

This report records diagnostic runs of the Understanding → SupportReview
pipeline with local Ollama `qwen3.5:9b`. Provisional references are comparison
material, not human gold labels. No accuracy is calculated, and no model output
is treated as correct merely because it matches a provisional reference.

## Root-cause inspection

Before the pipeline changed, the saved raw calls in
`qa/human-review-qwen35-9b-stage4d-20260928/` were inspected case by case. That
baseline attempted all 100 canonical cases and produced 56 accepted receipts
and 44 structural failures:

| Baseline structural cause | Cases |
| --- | ---: |
| Non-exact citation | 36 |
| Invalid rubric dimension or label | 5 |
| Duplicate judgment dimension | 1 |
| Academic record attached to a non-education claim | 1 |
| Understanding-call timeout | 1 |

The 36 citation failures were not validator false positives. Qwen shortened,
spliced, or inserted ellipses into source text—for example, returning only the
opening of a longer sentence—so the quotations were not exact substrings. The
validator correctly rejected every one.

The exact causes in the old pipeline were:

- Citation `document_id` and `quote`, rubric `dimension`, and rubric `label`
  were unconstrained strings in the provider schema. The prompt asked for
  exactness, but constrained decoding could still produce paraphrases and
  labels outside the rubric.
- Duplicate or cross-dimension judgments, stray/missing academic records, and
  non-claim target-ID collisions reached strict validation without a safe
  normalization step.
- The competency array could be interpreted as an exhaustive taxonomy
  checklist. Because `observed_skill` was a required string, Qwen filled all 18
  entries in `hr-stage4b-trap-comparison-impact`, using strings such as
  `"null"` and explanations that a skill was absent or unrelated.
- The old SupportReview prompt checked whether an explanation related to the
  source, but did not state strongly enough that negative, absent, unrelated,
  or merely not-demonstrated catalog entries must be rejected. It accepted all
  18 checklist entries in the database case.
- A comparison, metric, or numeric outcome was too easily routed to
  programming, quantitative analysis, impact, or a nearby domain competency.

## Pipeline changes

The pipeline still uses exactly two model stages. No judge agent or additional
LLM stage was added.

- The provider schema now enumerates allowed document IDs, exact source
  passages, rubric dimensions, and rubric labels. Deterministic normalization
  fails closed when a label does not belong to its selected dimension, and
  provenance validation remains strict after decoding.
- The Understanding prompt explicitly requires copying one supplied citation
  passage verbatim and prohibits ellipses, splicing, paraphrases, and invented
  quotations.
- Deterministic normalization fails closed on invalid/cross-dimension labels
  and duplicate judgments, repairs only non-claim ID collisions, removes stray
  academic records, supplies an unknown academic record for an education claim
  when necessary, and drops negative/placeholder competency suggestions.
- Understanding and SupportReview now say that competency suggestions must be
  positive demonstrated skills, never an exhaustive checklist. Absence,
  unsupported, unrelated, and `null` suggestions are invalid.
- SupportReview now rejects comparison/measurement alone as programming,
  quantitative analysis, impact, or unrelated domain evidence. Narrow
  deterministic gates enforce explicit programming actions/artifacts,
  quantitative methods, stated outcomes, and domain-specific signals for
  distinctive catalog competencies.
- No maximum number of competencies is imposed. A regression test retains 24
  positive cross-domain suggestions.

## Affected-case reruns

The 44 old structural failures plus the database all-competency trap were run
first. The initial targeted pass retained 40 accepted receipts and exposed four
non-claim target-ID collisions plus one provider timeout. After target-ID
normalization, four retries were accepted; the remaining provider timeout was
accepted on the final retry. Taken together, all 45 affected cases have an
accepted receipt in:

- `qa/human-review-qwen35-9b-stage4d-targeted-20260929/`
- `qa/human-review-qwen35-9b-stage4d-targeted-retry-20260930/`
- `qa/human-review-qwen35-9b-stage4d-targeted-retry2-20260930/`

These intermediate failures are retained as diagnostic evidence, not counted
as results of the final run.

## Final 100-case run

Run `qwen35-9b-stage4d-final3-20260930` used local `qwen3.5:9b`, a
16,384-token context, and a 180-second per-call timeout. Raw calls, hashes,
response IDs, SupportReview checks, accepted pipeline receipts, and comparison
differences are retained in
`qa/human-review-qwen35-9b-stage4d-final3-20260930/`.

| Domain | Attempted | Accepted receipts | Structural failures |
| --- | ---: | ---: | ---: |
| Civil | 12 | 12 | 0 |
| Computer science | 12 | 12 | 0 |
| Cybersecurity | 12 | 12 | 0 |
| Electrical/embedded | 10 | 10 | 0 |
| Interdisciplinary | 8 | 8 | 0 |
| Machine learning | 12 | 12 | 0 |
| Mechanical | 10 | 9 | 1 |
| Research | 10 | 10 | 0 |
| Semantic traps | 8 | 8 | 0 |
| Teaching | 6 | 6 | 0 |
| **Total** | **100** | **99** | **1** |

Final structural failures by cause were: provider timeout 1, non-exact citation
0, invalid rubric dimension/label 0, duplicate judgment dimension 0,
academic-record mismatch 0, and other schema/provenance failure 0. The timeout
was `hr-stage4b-mech-alternatives` during the Understanding call. An independent
substring audit of every citation in the 99 accepted receipts found 0 non-exact
citations.

Three isolated retries of `hr-stage4b-mech-alternatives` were retained in
`final3-retry`, `final3-retry2`, and `final3-retry3` directories. They failed in
`provider_student_understanding` after 180.17, 360.19, and 759.22 seconds,
respectively. The last retry followed a clean Ollama model unload/reload and
used a 600-second per-call transport timeout. These results confirm a
reproducible model-latency failure; no draft reached schema, citation, or
SupportReview validation in those attempts. The authoritative full-run result
therefore remains 99 accepted receipts plus 1 timeout.

Replaying all 99 accepted results through the latest deterministic guard code
produced 0 verdict changes and 0 supported-ID mismatches. Across those receipts,
Qwen proposed 132 competencies and 416 judgments. The final pipeline supported
62 competencies and 177 judgments; SupportReview or deterministic fail-closed
policy withheld the other 70 competency suggestions and 239 judgments. These
counts describe routing behavior, not correctness or accuracy.

### Required boundary checks

- `hr-stage4b-trap-comparison-impact` is fixed. Its final draft contains zero
  competency suggestions and its accepted receipt contains zero supported
  competencies. The database comparison supports investigation/comparison
  judgments only; it does not create programming, quantitative-analysis, or
  impact credit.
- `hr-stage4b-cs-cache-design` still caused Qwen to propose distributed
  systems, quantitative analysis, programming, and networking. SupportReview
  plus deterministic policy rejected all four, leaving zero supported
  competencies. Its explicit latency fall remains a measured outcome rather
  than being confused with quantitative-analysis competency.
- All 13 canonical bare-tool or bare-technology cases retain the named item as
  context and have zero supported competencies and zero supported judgments:
  AutoCAD, ETABS, SQL, Kali, Nessus, Arduino, Verilog, ANSYS, SolidWorks,
  PyTorch, Wireshark, BERT, and a paper mentioning machine learning. The
  multi-tool context case and publication-prestige trap satisfy the same
  context-only rule.

## Remaining semantic problems requiring human review

Structural acceptance is not a human correctness judgment. The following
model behaviors remain review questions:

- `hr-stage4b-teach-ta-title` treats the title “Teaching Assistant for
  Introduction to Programming” as demonstrated teaching instruction and
  `depth=applied`, although the source describes no instructional action. This
  is a clear semantic overreach by Qwen/SupportReview.
- `hr-stage4b-trap-action-verb` accepts `ownership=led` from “Spearheaded data
  migration activities” without a described ownership decision or scope.
- `hr-stage4b-trap-third-party` classifies the supervisor's threat-model and
  control-selection work as a student claim and supports `ownership=assisted`.
  The source does not state an applicant contribution.
- `hr-stage4b-research-preprint-method` omits programming competency despite
  the explicit statement that the applicant implemented a preprocessing
  pipeline.
- `hr-stage4b-teach-grading-only` accepts evaluation `described` for grading
  with a professor's rubric. A human should decide whether this describes
  evaluation of the applicant's work or only an assigned grading task.
- `hr-stage4b-research-peer-reviewed-explicit` supports statistics from “led
  the analysis” of a survey without a stated statistical method. Likewise,
  engineering-simulation suggestions inferred from CAD interference checks or
  structural design iteration need human boundary review.
- `hr-machine-learning-evaluation` supports measured impact for a held-out
  macro-F1 improvement. A human should decide whether the rubric intends model
  evaluation outcomes to count as impact or reserves impact for downstream
  effects.
- Team, third-party, and qualitative-coding cases still need a consistent human
  policy for retaining methods as contextual evidence while preventing
  unsupported applicant credit.

No canonical case, provisional reference, human-review final label, split,
scoring input, taxonomy mapping, or program-relevance field was changed. Every
canonical case remains pending; human final labels remain null and splits
remain unassigned.
