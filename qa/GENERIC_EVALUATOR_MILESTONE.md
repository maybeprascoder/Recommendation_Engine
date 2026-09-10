# Generic evaluator: first implementation milestone

This implements the generic interpretation boundary, not the full recommendation
product. No personal resume was sent to a model in this work. Live tests used
synthetic examples only. No paid subscription or API credits were purchased.

## Implemented

- Separate source-linked claims, qualitative judgments, academic records,
  competency suggestions, duplicate references, and clarification questions.
- Provisional versioned rubric for ownership, depth, evaluation, and impact,
  with category-specific guidance for technical and nontechnical evidence.
- Bounded interpretation and semantic-support-review calls through a replaceable
  HTTP client. Prompts and documents use separate roles; documents are untrusted.
- Native local Ollama with explicit context size and thinking disabled. No
  automatic provider fallback. Local mode rejects remote endpoints and cloud tags.
- OpenAI-compatible endpoint support with explicit output capability selection.
- Strict provenance, cross-reference, rubric-label, and review-coverage validation.
  Unknown dimensions remain unknown; rejected claims cannot grant child judgments.
- CLI `analyze`, offline recorded-response mode, exclusive output-file creation,
  and a Windows local-model launcher. Text/Markdown inputs only at this stage.
- Full source and rubric snapshots, hashes, requested/returned model identifiers,
  prompt fingerprint, and model response identifiers in the analysis audit.
- Thirty synthetic cases with review expectations and a live evaluation runner.

## Verification

- Full suite: **179 passed**, with 82 existing provisional-configuration warnings.
- After final field/prompt refinements: **46 focused and packaging tests passed**.
- Ruff and strict mypy: passed (17 core source files checked by mypy).
- Distribution checks exercise sdist, wheel, installed resources, and executable.
- Transport tests use an isolated HTTP server and cover modes, errors, refusals,
  incomplete output, redirects, credential separation, and native Ollama settings.

## Live findings

Local hardware reported an RTX 4060 laptop GPU with approximately 8 GB VRAM.
Already-installed Qwen 7B and 9B models were available. Kimi K2.6 Cloud registration
succeeded, but its inference request returned HTTP 401. The user then specified
no paid model use, and work switched to local inference; cloud sign-in is not needed.

The initial 7B run used Ollama's 4096-token default context and failed validation.
Native Ollama support now requests 16384 tokens explicitly. Qwen 3.5 9B produced
schema/provenance-valid results for the tutorial and unpublished-research cases
after prompt refinement. Inspection found that the tutorial was identified as
guided work and research-method evidence was recognized without a publication.
An early research run overstated ownership; later instructions and review guidance
addressed that case. This is not proof that ownership judgments are generally reliable.

Early GPA runs omitted education claim links; these were rejected rather than
silently accepted. The final two-GPA run passed validation and retained separate
8.2/10 and 3.6/4.0 records with the correct education claims and no conversion.
The final research and GPA runs took about 69 seconds each; the tutorial run
took about 39 seconds. These three smoke examples are not a broad model benchmark.
Synthetic outputs, failures, timings, and model responses are
kept under ignored `data/reviews/local-qwen-evals-*`. See each run's `results.json`
for the exact live outcome. Live runs take tens of seconds per small case; latency
and larger-document behavior still need work.

## Limits and next work

The 30 cases are prepared, not all model-validated. Passing structural validation
is different from passing expert review. The support reviewer uses the same model
and can repeat an interpretation error. Rubric descriptors have no expert validation.

Next: evaluate broader local cases and long documents, improve structured-output
reliability and latency, connect correction/confirmation, add sourced lookup tools,
and validate competency mapping before connecting these judgments to scoring.
PDF/OCR, web upload, live university research, program matching, and calibrated
admissions recommendations are not implemented by this milestone.
