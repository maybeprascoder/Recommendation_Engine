# Stage 4C human-review batch

`human_review_batch_stage4c.json` is a compact manifest of 30 existing
`review_id` values from [`human_review_cases.jsonl`](human_review_cases.jsonl).
It records each case's canonical domain, lineage group, source fingerprint,
immutable pre-review digest, and the reason it was selected. It does not copy
the source records, assign dataset splits, or contain numeric scoring data.

For each case, a reviewer should:

1. Read the exact `source.text` in the canonical JSONL record first.
2. Evaluate the provisional reference independently.
3. Use `model_prediction` only as comparison material; it is never gold.
4. Populate `human_review.final_label` only after deciding the label independently.
5. Set a reviewer ID and review timestamp, and record uncertainty or disagreements explicitly.
6. Preserve `UNKNOWN` unless the source supports a stronger conclusion; keep explicit absence narrow.
7. Never assign `Safe`, `Moderate`, or `Ambitious` labels, scores, probabilities, university relevance, or program-fit judgments in this dataset.

Run `python -m qa.human_review_batch` before review and after any manifest
maintenance. Validation requires 20–30 unique existing IDs, matching domains
and lineage groups, unchanged immutable record blocks, pending review status,
null final labels, and no scoring or admissions fields. Human adjudication may
change only the review fields in the canonical records; the batch manifest is a
pre-review integrity check and is not a gold-label export.
