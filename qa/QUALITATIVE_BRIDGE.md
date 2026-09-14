# Validated qualitative evidence → deterministic scoring

This task extends the existing understanding/confirmation pipeline. It adds no
evaluator, validator agent, external lookup, or program-data subsystem.

1. **What already existed.** `analyze_documents` made at most two model calls:
   `UnderstandingDraft` extraction and `SupportReview`. The draft contained cited,
   categorized claims, student/team/other/unknown attribution, duplicate references,
   academic records, bounded ownership/depth/evaluation/impact judgments, competency
   suggestions and questions. Exact quotations, unique IDs, complete review coverage,
   supported-ID lists, source hashes and rubric snapshots were already validated.
   Student confirmation, deterministic evidence evaluation, competency resolution,
   program scoring and replay also existed.

2. **Why it stopped before scoring.** Confirmation created generic self-reported
   Evidence with null quality/depth and `awaiting_approved_mapping`. Competency
   resolution skipped excluded evidence; direct evaluation rejected it. The existing
   mapping adapter could create a second, scoreable Evidence item, but its YAML was
   empty, its schema demanded a named expert/date/source, and its loader rejected
   provisional evidence rules. Category matching also lacked a supported competency
   requirement and overlapping mappings could create multiple contributions.

3. **Exact bridge implemented.** After existing provenance/support validation and
   student confirmation, a mapping requires the exact rubric hash, the claim's category,
   every configured judgment label to be supported and confirmed unchanged, and a
   supported suggestion for the destination competency on that same claim. Unknown
   judgments never match. The highest configured priority wins once per claim and
   competency. The emitted Evidence remains self-reported, contains configured
   quality/depth labels, and carries a structured mapping trace. Routing is restricted
   to the selected evidence-rule ID so other rules sharing its kind cannot grant
   unreviewed adjacent competencies. The original claim remains preserved and excluded.
   Reconfirmation replaces earlier projections from the same interpretation.

4. **Reuse of qualitative_mappings.** The existing YAML, model, schema, loader and
   confirmation adapter were extended. `provisional` and `priority` were added;
   validation metadata can be null for provisional mappings. Non-provisional mappings
   still require validation metadata and a validated evidence rule. The loader validates
   rubric/quality/depth labels, references, duplicate conditions and priority ambiguity.
   Provisional records warn, count in the CLI, and propagate to the report flag.
   `approved_mapping_id` and `awaiting_approved_mapping` keep their legacy serialized
   names for compatibility; neither implies per-student expert approval. A new
   `qualitative_mapping` trace records mapping version, mapping hash, taxonomy version,
   rubric hash, selected rule, provisional status and supporting IDs.

   The v2 seed contains 24 provisional mappings: four categories (project, work,
   research, publication), two existing competencies (programming, machine learning),
   and three alternatives per pair. No competency nodes were added. All new seeds have
   `validated_by: null` and `source: null`; they are product defaults, not calibrated
   claims about outcomes. The rubric itself was preserved.

   | Supported conditions | Quality label/value | Depth label/factor | Priority |
   | --- | --- | --- | --- |
   | depth=applied | basic / 1.0 | applied / 1.0 | 10 |
   | depth=designed or investigated | substantive / 2.0 | designed_or_investigated / 1.25 | 20 |
   | designed/investigated + compared + measured | evaluated_outcome / 3.0 | designed_or_investigated / 1.25 | 30 |

   These values live only in YAML. Unknown ownership does not become leadership or an
   ownership penalty. Existing verification, recency, combination and level thresholds
   remain unchanged. The existing research-venue ladder remains available for legacy
   structured evidence; the new qualitative bridge uses a separate intrinsic ladder.

5. **Every file changed or added.** Repository-relative manifest:

   - `README.md`: explain the now-active bridge and remaining calibration work.
   - `cli.py`: count provisional qualitative mappings.
   - `data/schemas/qualitative_mappings.schema.json`: provisional/priority fields and nullable metadata.
   - `data/taxonomy/evidence_rules.yaml`: two provisional intrinsic competency routes.
   - `data/taxonomy/ladders.yaml`: intrinsic quality and activity depth labels.
   - `data/taxonomy/qualitative_mappings.yaml`: 24 versioned provisional mappings.
   - `src/unihive/competency.py`: scope mapped evidence to its selected rule.
   - `src/unihive/evidence.py`: enforce selected-rule evaluation and update exclusion wording.
   - `src/unihive/llm/prompts/support_review_v1.txt`: explicit unsupported prestige/metadata restrictions; prompt v3.
   - `src/unihive/llm/prompts/understanding_v1.txt`: explicit memory-derived enrichment restrictions; prompt v3.
   - `src/unihive/llm/understanding.py`: material depth clarification fallback, accurate limitations and prompt version.
   - `src/unihive/models.py`: structured mapping provenance on Evidence.
   - `src/unihive/response.py`: include provisional mappings in report disclosure.
   - `src/unihive/taxonomy.py`: mapping validation, provisional support, deterministic priority integrity and warnings.
   - `src/unihive/understanding_review.py`: supported competency gate, mapping selection and provenance projection.
   - `tests/test_profile_followup.py`: expect the newly configured ML evidence kind.
   - `tests/test_qualitative_bridge.py`: mocked end-to-end examples and adversarial bridge regressions.
   - `tests/test_taxonomy.py`: provisional mapping and invalid configuration cases.
   - `tests/test_understanding_review.py`: retain calibrated-mapping coverage with supported skill evidence and appropriate intrinsic labels.
   - `tests/understanding_samples.py`: shared mocked two-pass sample builder.
   - `web/README.md`: confirmation/mapping behavior and compatibility documentation.
   - `web/understanding.js`: accurate scoring and self-report disclosure.
   - `qa/QUALITATIVE_BRIDGE.md`: this report.
   - `qa/qualitative-bridge-pytest.txt`: final full-suite output.
   - `qa/qualitative-bridge-ruff.txt`: Ruff result.
   - `qa/qualitative-bridge-mypy.txt`: strict mypy result.
   - `qa/qualitative-bridge-frontend.txt`: frontend contract results.

6. **Project flow.** The TODO sample has supported applied depth and programming;
   ownership, evaluation and impact remain unknown. Confirmation selects basic/applied
   self-reported evidence. Existing arithmetic gives 1 × 1 × 1 × 0.8 × 0.8 = 0.64,
   resolving to introductory programming. The BERT sample has supported designed,
   compared and measured judgments plus machine learning. It selects only the
   evaluated_outcome mapping, producing 3 × 1 × 1.25 × 0.8 × 0.8 = 2.4 and developing
   machine learning. These are internal competency contributions, not final student
   scores or admission probabilities. The NLP observation remains a supported skill
   with null taxonomy ID because no NLP node exists. Ownership remains unknown.
   Tests continue through existing target scoring and byte-identical audit replay.

7. **Publication flow.** The exact Journal XYZ example retains the publication,
   first-author statement, transformer segmentation topic and venue in the cited claim.
   Metadata alone does not establish applied/designed/investigated depth; all dimensions
   remain unknown and a personal method/evaluation clarification is generated. It is
   legitimate self-reported evidence, but is not assigned invented scoring inputs.
   A second publication fixture adds controlled ablations, baseline comparisons and a
   measured Dice improvement. Supported investigated/compared/measured labels plus ML
   then map through the same intrinsic ladder into deterministic competency resolution,
   target scoring and replay. Neither fixture gets a venue tier, citation count,
   peer-review assumption, or an authorship multiplier inferred from depth.

8. **What remains self-reported.** All imported and mapped accomplishments, production
   deployment, measured improvements, authorship and publication claims. Source support
   verifies interpretation consistency only. The existing self-report factor is 0.8;
   the unchanged verified-present factor is 1.0. Unknown remains distinct from confirmed
   absence and does not become zero readiness.

9. **What may be verified later.** Trusted external records may corroborate publication
   existence/status/authorship, documented work or project outcomes, or educational
   credentials. A future authorized verification workflow can use `VERIFIED_PRESENT`
   for the supported scope. Venue/institution enrichment would require trusted data
   and its own configuration. No automatic upgrade or new verification state was added.

10. **LLM controls.** Proposed source-linked statements, categories, attribution,
    bounded qualitative labels, catalog-bound skill suggestions and questions. It does
    not provide final numeric scores, ladder values, weights or target relevance.

11. **Validator controls.** The single existing SupportReview decides semantic support,
    uncertainty and rejection for each proposed target and identifies duplicate work.
    Deterministic validation enforces schema, quotations, references, complete review
    coverage, hashes and derived support lists. The second model can still make errors;
    mocked tests demonstrate pipeline behavior, not live-model semantic accuracy.

12. **Deterministic code controls.** Eligible unchanged confirmations, mapping matches,
    priority selection, supported competency routing, quality/depth label projection,
    provenance, verification/recency factors, diminishing returns, competency levels,
    existing target demand comparisons and audit replay. Intrinsic activity attributes
    remain separate from later target relevance; no universal final score was added.

13. **Intentionally unimplemented.** External institution/publication lookups, venue
    rankings, university/program databases, new target relevance models, portfolio work,
    probabilities and multi-agent frameworks. The program-data recommendation gate and
    existing scoring formula were not changed. Broader competency coverage and empirical
    calibration remain future configuration work. The current provider and rubric
    contracts were reused; no live LLM calls or private-claim internet searches ran.

14. **Full pytest results.** **249 passed, 4039 warnings in 47.66s; no failures or skips.**
    See `qualitative-bridge-pytest.txt` for the full output. Command:
    `.venv/Scripts/python.exe -m pytest -q --disable-warnings --tb=short --basetemp=.pytest_tmp_bridge_full_02`.
    Warnings include repeated disclosure of provisional configuration. Run with the
    repository virtual environment and a fresh repository-local
    `--basetemp` because the Windows default pytest temporary directory was inaccessible.
    The initial baseline produced 186 passes and 34 temporary-directory setup errors.
    The first complete post-change run found one obsolete follow-up evidence-kind
    expectation (248 passed); that assertion was updated to include the new route.

15. **Other checks.** Ruff over the entire repository passes. Strict mypy passes for
    all 19 configured deterministic source files. The existing frontend contract suite
    passes all 12 checks. `git diff --check` passes. Raw results are saved alongside
    this report. No checks were skipped or weakened to bypass a failure.
