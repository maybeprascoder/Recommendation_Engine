# Qwen 3.5 9B provisional-data diagnostics

Run `stage4d-qwen35-9b-20260928` used the existing Understanding →
SupportReview pipeline with local Ollama `qwen3.5:9b`. The Stage 4C manifest
ran first, followed by the other 70 canonical cases. Provisional references
were comparison material, not gold labels, so this report does not calculate
accuracy.

The run attempted all 100 cases. It produced 56 accepted pipeline receipts and
44 structural failures. Of the failures, 36 violated exact-citation rules, five
used an invalid rubric dimension or label, one duplicated a judgment dimension,
one omitted a required academic record, and one timed out during the first
Understanding call. Raw completions, call-level prompt versions and hashes,
response IDs, source hashes, failures, and accepted results are retained in
`qa/human-review-qwen35-9b-stage4d-20260928/`.

| Domain | Attempted | Accepted | Structural failures |
| --- | ---: | ---: | ---: |
| Civil | 12 | 4 | 8 |
| Computer science | 12 | 9 | 3 |
| Cybersecurity | 12 | 8 | 4 |
| Electrical/embedded | 10 | 6 | 4 |
| Interdisciplinary | 8 | 1 | 7 |
| Machine learning | 12 | 5 | 7 |
| Mechanical | 10 | 6 | 4 |
| Research | 10 | 6 | 4 |
| Semantic traps | 8 | 8 | 0 |
| Teaching | 6 | 3 | 3 |

All 13 accepted bare-tool or bare-technology cases kept the named item as
context and produced zero supported competencies and zero supported judgments.
This includes AutoCAD, ETABS, SQL, Kali, Nessus, Arduino, Verilog, ANSYS,
SolidWorks, PyTorch, Wireshark, BERT, and a paper mentioning machine learning.
The publication-prestige trap also produced context only. SupportReview rejected
12 of 71 proposed competency suggestions and 179 of 256 proposed judgments in
the 56 accepted receipts; those corrections are useful diagnostics, not a
measure of correctness.

## Likely model mistakes

- `hr-stage4b-trap-comparison-impact`: the source only compares two database
  engines by latency and memory. The draft created all 18 allowed competency
  nodes, usually with text saying the competency was not evidenced, and
  SupportReview accepted every one. This is the highest-priority routing and
  SupportReview failure.
- `hr-stage4b-cs-cache-design`: the accepted result infers programming from
  conducting load tests and infers `distributed_systems` from a cache in a
  catalog service. It also routes the latency comparison to
  `quantitative_analysis`. The source states design, comparison, and a measured
  result, but does not state implementation, coding, or a distributed system.
- `hr-machine-learning-evaluation`: SupportReview correctly rejects ownership
  `led`, but accepts programming because inference was deployed and accepts
  `quantitative_analysis` because baselines and macro-F1 were compared. Both
  competency routes rely on implication rather than an explicit performed
  method.
- `hr-stage4b-trap-metric-quant`: input validation is routed to `security`
  without a stated security purpose. The before/after error-count analysis may
  support `quantitative_analysis`, but it does not itself establish security.
- `hr-stage4b-teach-grading-only`: grading with the professor's rubric becomes
  evaluation `described` and entering scores becomes impact `reported`. Those
  labels appear to confuse evaluating students with evaluation and impact of
  the applicant's work.
- `hr-stage4b-research-preprint-method`: the accepted result omits programming
  despite the explicit statement that the applicant implemented the
  preprocessing pipeline.

SupportReview did catch several first-pass mistakes. It rejected competencies
for the isolated “beam reaction was 42 kN” result, rejected `led` for
“spearheaded,” and rejected absence claims derived from a silent resume. These
should remain regression cases.

## Likely provisional-reference mistakes

- `hr-stage4b-cs-cache-design` says the applicant “implemented” cache
  invalidation and assigns programming, although the source only says
  “designed.” Its `distributed_systems` route also needs evidence beyond a
  service cache mention.
- `hr-stage4b-ml-feature-design` says a feature/evaluation pipeline was
  implemented and assigns programming, although the source states design,
  cross-validation, and comparison without explicit coding. The real model
  draft did not propose programming, but its paraphrased citations caused a
  structural failure, so it is not an accepted prediction.
- `hr-machine-learning-evaluation` contains two machine-learning suggestions
  for one activity and separately claims missing taxonomy coverage for NLP
  classification even though the existing machine-learning node represents the
  work.
- `hr-stage4b-trap-comparison-impact` provisionally assigns programming even
  though comparing database engines does not explicitly state coding.
- `hr-stage4b-soc-team-attribution` assigns investigation depth, evaluation,
  and security to a team statement that explicitly withholds the applicant's
  contribution. A human should decide whether those annotations are retained
  solely as third-party/team evidence or removed from applicant competencies.

## Genuine ambiguities

- In `hr-machine-learning-evaluation`, a held-out macro-F1 improvement is a
  measured evaluation result. A reviewer must decide whether the current
  `impact=measured` rubric intentionally includes model-evaluation outcomes or
  is reserved for downstream, real-world impact.
- In the cache case, service caching may be evidence of distributed-systems
  work in context, but the text does not describe distribution. The latency
  comparison may be quantitative analysis or may belong only in evaluation and
  measured result fields.
- `hr-stage4b-research-thematic-coding` supports qualitative research, but
  ownership could be `led` because the applicant created the codebook and coded
  all transcripts, or `shared` because a second coder participated in the
  comparison.
- `hr-stage4b-trap-resume-silent` explicitly states absence of information, not
  absence of cryptography experience. Reviewers should preserve `UNKNOWN` for
  the skill while deciding how to encode the narrowly scoped absence of resume
  evidence.
- Team and third-party cases need a consistent policy for annotating methods
  that are stated for the team or supervisor while keeping applicant ownership
  unknown and preventing applicant competency credit.

## Prioritized human-review shortlist

1. `hr-stage4b-trap-comparison-impact` — all-node competency routing and
   SupportReview acceptance.
2. `hr-stage4b-cs-cache-design` — unsupported implementation, programming,
   distributed-systems, and quantitative-analysis boundaries.
3. `hr-stage4b-ml-feature-design` — programming without explicit coding and
   action-verb ownership; inspect the retained failed draft.
4. `hr-machine-learning-evaluation` — duplicate provisional ML suggestions,
   stale NLP gap, programming/quantitative routes, ownership, and the meaning
   of measured impact.
5. `hr-stage4b-soc-team-attribution` and `hr-stage4b-trap-third-party` — team
   and supervisor evidence without applicant contribution.
6. `hr-stage4b-trap-metric-quant` and
   `hr-stage4b-civil-load-number-trap` — quantitative-analysis routing from
   measured comparison versus a bare numeric result.
7. `hr-stage4b-teach-grading-only` — teaching, evaluation, impact, and assisted
   ownership boundaries.
8. `hr-stage4b-research-preprint-method`,
   `hr-stage4b-research-thematic-coding`, and
   `hr-stage4b-trap-resume-silent` — explicit implementation, qualitative
   ownership, publication inference, and narrowly scoped absence.

The canonical JSONL remains unchanged: every case is still pending, every
`human_review.final_label` remains null, and every split remains unassigned.
The next action is for a human reviewer to open the shortlist cases beside their
canonical records and saved diagnostic artifacts, adjudicate the source first,
then record final labels, uncertainty, disagreements, reviewer ID, and review
timestamp in the canonical workflow.
