# Human-review dataset foundation

## Review format

[`human_review_cases.jsonl`](human_review_cases.jsonl) contains one editable JSON
record per source case. Each record keeps these blocks separate:

- `source`: exact source text, fixture path and case ID, plus hashes for the text,
  case, and fixture file.
- `provisional_reference`: the synthetic annotation and its support review.
- `model_prediction`: a self-contained, hashed snapshot of an existing live-model
  annotation and run metadata, or an explicit `not_available` state. Its original
  ignored run path is retained as provenance and cross-checked when present;
  offline fixture replays are not presented as model predictions.
- `human_review`: reviewer identity, final label, uncertainty, disputes, and notes.
- `leakage_control`: source fingerprint, semantic lineage group, and data split.

Each label retains claims, attribution, presence or absence, contexts and tools,
demonstrated methods, competency suggestions, ownership, depth, evaluation,
impact, questions, unassessed facts, and per-item support verdicts. It contains no
numeric scoring fields.

Eight pending records cover computer science, machine learning, cybersecurity,
civil, mechanical, electrical/embedded, qualitative research, and teaching. Five
have historical live-model predictions; three truthfully record that none exists.

Run `python -m qa.human_review_dataset` to validate the file. Validation rejects
changed or missing source references, altered embedded prediction snapshots,
invalid rubric labels, unknown competency IDs, invalid citations, incomplete
support reviews, duplicate IDs, and inconsistent review states. A locally present
original model artifact is also hash-checked. `--write-seed` requires the original
local artifacts and is only for rebuilding the pending seed; do not use it after
adjudication starts.

## From provisional to human-reviewed

A reviewer compares the source, provisional reference, and model prediction. They
write an independently chosen `human_review.final_label`, set `reviewer_id` and
`reviewed_at`, resolve every open dispute, and then change `status` from `pending`
to `adjudicated`. Copying a provisional or model label is never performed by the
builder or validator. Unknown labels remain valid when the source does not support
a stronger conclusion.

`uncertain_fields` records explicit unknown judgments, clarification questions,
unassessed facts, and uncertain support verdicts. Reviewers add differences of
interpretation to `disputed_fields`, preserving the provisional value, model
value, chosen human value, rationale, and whether the dispute is open or resolved.
An adjudicated record cannot retain an open dispute.

## Later instruction-tuning export

A later exporter should accept only validated `adjudicated` records and emit the
exact source text as input with only the human final label as the target. It should
exclude provisional references, model predictions, reviewer metadata, disputes,
and all scoring data. No tuning export is implemented or run in this stage.

Before export, assign splits by `lineage_group`, never by individual row. All
exact-source duplicates share `source_fingerprint`; paraphrases and related
semantic probes must be assigned the same lineage group during review. Freeze the
group-to-split manifest before producing train, validation, or test files, and
reject any fingerprint or lineage group occurring in more than one split.

## Stage 4 answers

**A. Is the dataset format ready for manual adjudication?** Yes. The editable
format and structural/provenance validation are ready.

**B. How many representative cases are prepared?** Eight, one for each requested
area.

**C. What still needs actual human review?** All eight final labels, every
remaining uncertainty, any disagreement entries, reviewer identity and review
time, and lineage/split confirmation. The three cases without live predictions do
not need synthetic predictions to be adjudicated.

**D. Are we ready to start manually converting provisional examples into gold
labels?** Yes. Gold status begins only when a named reviewer supplies and validates
an independent final label.
