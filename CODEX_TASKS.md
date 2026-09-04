# Codex task sequence — UniHive engine

Run these **one at a time**, in order. Each is a separate Codex task. After each
one: read the diff, run the tests yourself, commit. Do not queue two together.

Prerequisite: repo initialised, `AGENTS.md` at root, `docs/` containing both
spec markdown files, all committed.

---

## Task 0 — Scaffold and types

> Set up the project skeleton for the UniHive engine exactly as described in
> AGENTS.md. Create the directory layout, `pyproject.toml` (Python 3.11+,
> pydantic v2, pyyaml, pytest, ruff, mypy), and `src/unihive/models.py`
> containing the core pydantic types only — no logic yet.
>
> Types to define:
> - `EvidenceState` enum: VERIFIED_PRESENT, SELF_REPORTED_PRESENT,
>   CONFIRMED_ABSENT, UNKNOWN, NOT_APPLICABLE
> - `ReadinessBand` enum: EMERGING, DEVELOPING, COMPETITIVE, STRONG
> - `Confidence` enum: LOW, MEDIUM, HIGH
> - `EligibilityStatus` enum: ELIGIBLE, CONDITIONALLY_ELIGIBLE,
>   NOT_CURRENTLY_ELIGIBLE, UNKNOWN
> - `CompetencyLevel` enum (an ordinal scale — pick and document one)
> - `Evidence`: id, kind, raw_text, state, quality, depth, recency, source,
>   extraction_confidence
> - `StudentCompetency`: competency_id, level, state, contributing_evidence_ids
> - `StudentProfile`: academic history, normalized GPA, courses, skills,
>   projects, research, work, goals, constraints, tests, list of Evidence
> - `ProgramConfig`: program_id, university, degree, demand profile
>   (competency_id → required level + weight), eligibility rules, dimension
>   emphasis, `version`, `source_url`, `verified_on`, `provisional`,
>   `validated_by`
> - `AuditRecord`: engine_version, taxonomy_version, program_config_version,
>   evidence_ids_used, missing_fields, source_urls, timestamp
> - `Assessment`: the six separate outputs from AGENTS.md invariant 4, plus
>   `audit: AuditRecord`, plus `not_assessed: list[str]`. No aggregate field.
>
> Also write `tests/test_architecture.py`, which walks the import graph of
> `src/unihive/` and asserts that no module outside `src/unihive/llm/` imports
> `anthropic`, `openai`, `httpx`, `requests`, or `socket`.
>
> No business logic in this task. Stop after the types and that one test pass.

---

## Task 1 — Taxonomy schema, loader, validator

> Implement the competency taxonomy layer per Build Spec §3 and §4.
>
> Write JSON Schemas in `data/schemas/` for `competencies.yaml`,
> `evidence_rules.yaml`, `ladders.yaml`, and `aliases.yaml`. A competency node
> has: id, name, field(s), parent/child relationships, CIP anchor (nullable),
> description, `provisional`, `validated_by`, `source`.
>
> Implement `src/unihive/taxonomy.py`: load, schema-validate, check referential
> integrity (no dangling parent ids, no cycles), expose lookup by id and alias,
> and expose a `version` string derived from a content hash of the taxonomy
> files. Loading must raise on invalid data and emit a warning listing every
> `provisional: true` node.
>
> Seed `data/taxonomy/competencies.yaml` with the competency names explicitly
> mentioned in `docs/engine_build_spec_v1.md` only — networking, operating
> systems, cryptography, statistics, machine learning, distributed systems,
> programming, security, policy/governance, and the others named in the specs.
> Mark every one `provisional: true` with `validated_by: null`. Do not invent
> additional nodes to reach a target count; a human is authoring those.
>
> Tests: valid file loads; malformed file raises; cycle raises; dangling
> reference raises; alias lookup resolves; version hash is stable across
> reloads and changes when content changes.

---

## Task 2 — Evidence → competency resolution

> Implement `src/unihive/evidence.py` and `src/unihive/competency.py`,
> covering Build Spec §4 and Experience doc §4 Principle 1.
>
> `evidence.py`: quality ladders loaded from `data/taxonomy/ladders.yaml` (the
> research-venue ladder in Experience doc §4 is the reference shape). Handle the
> five evidence attributes: quality, relevance, depth, verification state,
> recency. Recency takes an explicit `as_of` date parameter — never read the
> clock.
>
> `competency.py`: given a `StudentProfile` and the taxonomy, produce
> `list[StudentCompetency]`. Rules:
> - Multiple pieces of evidence for one competency combine with diminishing
>   returns — one strong item outranks two weak ones. Load the curve shape from
>   config; do not hardcode it.
> - A competency with no supporting or contradicting evidence gets state
>   `UNKNOWN`, not level zero.
> - `CONFIRMED_ABSENT` is a distinct state from `UNKNOWN` and they must not
>   collapse anywhere in this module.
> - Return an explanation trace per competency: which evidence contributed and
>   how much.
>
> This module is program-independent — it must not import anything about
> programs or demand profiles. Add a test asserting that.
>
> Tests: one top-venue first-author paper produces a higher ML level than two
> preprints; unknown stays unknown; confirmed-absent is distinguishable from
> unknown in the output; resolution is deterministic across 100 runs.

---

## Task 3 — Deterministic eligibility engine

> Implement `src/unihive/eligibility.py` per Build Spec §5.4.
>
> Rules evaluated: required prior degree, minimum GPA, mandatory coursework,
> English score, GRE requirement, work-experience requirement,
> citizenship/residency, deadline and intake availability. Rules and their
> thresholds come from the program's YAML, each with a `source_url`.
>
> Return an `EligibilityResult` with the status enum, a per-rule breakdown
> (`PASS | FAIL | UNKNOWN | NOT_APPLICABLE`) with the source link for each, and
> a list of what would need to be provided to resolve each UNKNOWN.
>
> A missing input yields `UNKNOWN` for that rule, and any UNKNOWN rule blocks a
> clean `ELIGIBLE` verdict — the overall status becomes
> `ELIGIBILITY_UNKNOWN`. A rule may never be assumed passed.
>
> No LLM, no network, no inference. Tests must cover each rule individually
> plus the unknown-blocks-eligible case and the conditional case.

---

## Task 4 — Scoring core and bands

> Implement `src/unihive/scoring.py` per Build Spec §4 and §5.5.
>
> Core: `Readiness(s,p) = Σ_k Demand(p,k) × Match(StudentCompetency(s,k),
> ExpectedLevel(p,k))`, over competencies with a known state only. Competencies
> in state UNKNOWN are excluded from both numerator and denominator and are
> collected into `not_assessed`. CONFIRMED_ABSENT contributes a real shortfall.
>
> Then:
> - Map the continuous result to a `ReadinessBand` using cutoffs from
>   `data/bands.yaml`, versioned.
> - Compute `data_confidence` from the ratio of verified / self-reported /
>   unknown evidence weighted by the demand of the competencies involved — a
>   large unknown in a high-demand competency should drop confidence hard.
> - Apply profile-shape rules from Experience doc §4 Principle 3: hard-
>   prerequisite floors (flagged, never silently averaged away) and coherence.
>   Keep these to a handful, each defensible in one sentence, each loaded from
>   config, each named in the trace.
> - Return the full explanation trace: per-competency contribution, demand
>   weight, evidence behind it, and what was excluded as unknown.
>
> Populate all six separate outputs on `Assessment`. Do not compute an
> aggregate.
>
> Tests as specified in Task 5 — write the module here, tests next.

---

## Task 5 — The invariant test suite

> Write `tests/test_invariants.py` as property-based tests using `hypothesis`,
> covering the invariants in AGENTS.md. Build a profile/program generator
> first. Required properties:
>
> 1. **Unknown is not zero**: for any profile, flipping any competency from
>    UNKNOWN to CONFIRMED_ABSENT never increases readiness.
> 2. **Unknown lowers confidence, not readiness**: flipping UNKNOWN to
>    VERIFIED_PRESENT at the same demonstrated level never decreases readiness
>    and never decreases confidence.
> 3. **Monotonic in evidence quality**: upgrading one piece of evidence up its
>    quality ladder never lowers readiness for a program demanding that
>    competency.
> 4. **Determinism**: identical input scored 100 times yields identical
>    serialized output.
> 5. **Program relativity**: there exist profiles whose readiness ordering
>    inverts between two programs with different demand profiles. (Assert the
>    engine can produce this, using the Experience doc §4 Student A / Student B
>    example as a concrete fixture.)
> 6. **Separation**: `Assessment` exposes six distinct reads and no aggregate;
>    eligibility never influences the readiness number.
>
> Also write `tests/test_no_probabilities.py`: serialize a range of assessments
> to JSON and assert the output contains no `%`, "chance", "probability",
> "odds", or "likelihood", and no float field named like a probability.
>
> If any property fails, fix `scoring.py` — do not weaken the property.

---

## Task 6 — Alternative pathways

> Implement `src/unihive/alternatives.py` per Build Spec §6.
>
> Surface an alternative path only when **all** hold: its band is at least one
> full band higher than the chosen path; that difference rests on
> medium/high-confidence evidence rather than on missing information; it stays
> aligned with the student's stated interest or career goal; the student has not
> previously rejected that field. Maximum two alternatives.
>
> No numeric threshold anywhere in this module — the rule is categorical.
> Return the delta and the reasoning for each alternative, and the reason for
> suppression when one is filtered out (that's needed for debugging and for the
> audit record).
>
> The chosen path is never removed or replaced in the output. Tests must
> include: a higher-band alternative resting on unknowns is suppressed; a
> previously rejected field is suppressed; more than two candidates truncates to
> two; the chosen path always survives.

---

## Task 7 — Portfolio construction

> Implement `src/unihive/portfolio.py` per Build Spec §5.6. Given scored
> candidates and student constraints (budget, funding need, location, career
> alignment, data confidence), build a balanced list of 8-12 programs across
> Safe / Target / Ambitious — not the top N by score.
>
> Balance is its own objective: the result must contain genuine safeties.
> Encode the target distribution in config. If constraints make a balanced list
> impossible (e.g. no affordable safeties in the candidate set), return the best
> available list plus an explicit `unmet_constraints` list — never silently
> return an unbalanced list.
>
> Tests: a candidate set that is entirely ambitious produces a populated
> `unmet_constraints`; budget filters are respected; output size stays in range.

---

## Task 8 — Next-best-question

> Implement `src/unihive/questions.py` per Build Spec §7 and Experience doc §2
> Phase 2. Given a current `Assessment`, rank candidate questions by how much
> resolving them would narrow the assessment — highest-uncertainty-first, where
> uncertainty is weighted by the demand of the competency it would resolve.
>
> Deterministic. Question bank in `data/questions.yaml`, each entry declaring
> which competency or field it resolves. Return the ranked list with the
> expected effect of each ("this would resolve networking, currently unknown
> and high-demand for your target").

---

## Task 9 — LLM extractor

> Implement `src/unihive/llm/extractor.py`. Raw resume text or free-text input
> → a `StudentProfile` of `Evidence` objects.
>
> Requirements:
> - Prompt templates live as files in `src/unihive/llm/prompts/`, versioned,
>   never inline strings.
> - Output is JSON validated against the pydantic model. On validation failure,
>   retry once with the error, then fail loudly — never coerce or patch.
> - Every extracted item carries `state`, `source` (the span it came from), and
>   `extraction_confidence`.
> - Anything not clearly stated in the input is `UNKNOWN`. The prompt must
>   explicitly forbid inferring a skill from an adjacent one.
> - Produce a `confirmation_payload`: the extraction rendered for the student to
>   confirm or correct before it is scored.
> - Tests run against recorded fixtures with the API mocked. No test may make a
>   network call.

---

## Task 10 — Narrator, report, CLI, audit

> Three pieces:
>
> 1. `src/unihive/report.py` — assemble the six-section report *structure* from
>    Experience doc §3 as pure data: what we understand about you, strengths,
>    gaps (confirmed only, never unknowns), chosen path + alternatives, top 3
>    actions ranked by impact-per-effort, what we can't assess yet. Each action
>    states which band it would move and why, computed by re-running `scoring.py`
>    with the hypothetical evidence added — that simulation is deterministic.
>
> 2. `src/unihive/llm/narrator.py` — turn that frozen structure into prose. It
>    receives the finished `Assessment` and may not recompute, reorder, or
>    re-rank anything. The prompt must forbid introducing any fact not present
>    in the input, and forbid percentages or probability language.
>
> 3. `cli.py` and `src/unihive/audit.py` — CLI with `--score-only` (runs the
>    full deterministic path with no API key), `--profile`, `--program`,
>    `--json`. Prints the count of provisional configs in use. Every run emits
>    an `AuditRecord`; add a `replay` command that reproduces a past assessment
>    from its audit record and asserts byte-identical output.
