# AGENTS.md — UniHive Admissions Intelligence Engine

You are working on the UniHive engine. Read this file fully before any task.
The authoritative specs are in `docs/`. When this file and the specs conflict,
this file wins for *code structure*; the specs win for *product behaviour*.

## What this system is

Given a student's evidence and a target program, produce an honest, auditable,
reproducible read on where they stand and what to do next. It is a diagnosis
engine. The school list is a downstream by-product.

## The architectural boundary (the whole design)

The LLM sits **around** the deterministic core, never **inside** the number.

```
raw student input
      │
      ▼
[LLM]  extractor ──────► structured Evidence  ──► student confirms/corrects
                                │
                                ▼
[DETERMINISTIC]   competency resolution → eligibility → scoring → bands
                                │
                                ▼
[LLM]  narrator  ◄──── scored Assessment object (frozen, never re-derived)
```

**Enforced rule:** only modules under `src/unihive/llm/` may import an LLM SDK
or make a network call. Everything else is pure Python over local data. There
is a test that walks the import graph and fails if this is violated
(`tests/test_architecture.py`). Do not weaken or skip that test.

## Non-negotiable invariants

These are correctness properties, not preferences. Every one has a test. If a
task appears to require breaking one, stop and say so in your summary instead
of breaking it.

1. **Unknown is never zero.** `EvidenceState.UNKNOWN` means "not yet assessed."
   It lowers *confidence*, never *readiness*. For any profile, flipping a
   competency from `UNKNOWN` to `CONFIRMED_ABSENT` must never raise readiness.
   Never write `weight * 0.0` for an unknown; unknown competencies are excluded
   from the readiness denominator and recorded in `not_assessed`.

2. **Determinism.** Scoring is a pure function. No RNG, no `datetime.now()`
   inside scoring (pass `as_of` explicitly for recency), no dict-ordering
   dependence, no LLM calls. Same input → byte-identical output, always.

3. **No probabilities, ever.** Readiness is one of
   `EMERGING | DEVELOPING | COMPETITIVE | STRONG`, paired with a confidence
   label `LOW | MEDIUM | HIGH`. Never emit an admission percentage, chance,
   odds, or likelihood. No field in any output object may be a probability.
   `tests/test_no_probabilities.py` scans serialized output for `%`, "chance",
   "probability", "odds", "likelihood" and fails on a hit.

4. **Six outputs stay separate.** `Assessment` has exactly these top-level
   reads and no aggregate: `pathway_readiness`, `program_alignment`,
   `eligibility`, `preference_fit`, `admissions_outlook`, `data_confidence`.
   Do not add `overall_score`, `total`, `final_score`, or any field that
   collapses them. Reject that refactor if asked for it.

5. **Eligibility ≠ readiness.** Separate axes, separate types. Eligibility is
   `ELIGIBLE | CONDITIONALLY_ELIGIBLE | NOT_CURRENTLY_ELIGIBLE | UNKNOWN`,
   produced only by deterministic rules with source links. Never blend it into
   a readiness band.

6. **No magic numbers in Python.** Every weight, threshold, band cutoff, and
   ladder value lives in versioned YAML under `data/`. Code loads them. A
   literal float used as a weight in a `.py` file is a bug.

7. **Everything is reproducible.** Every `Assessment` carries an
   `AuditRecord`: engine version, taxonomy version, program-config version,
   evidence IDs used, what was missing, source URLs, and confidence. An
   assessment that can't be replayed from its audit record is broken.

8. **No invented facts.** If evidence doesn't state it, it's `UNKNOWN`. Never
   infer a competency from an adjacent one. Never generate program data,
   deadlines, GPA cutoffs, or requirements — those come from `data/programs/`
   with a `source_url` and `verified_on` date, or they don't exist.

## Repo layout

```
docs/                         specs (read-only reference)
data/
  schemas/                    JSON Schema for every YAML file below
  taxonomy/
    competencies.yaml         the ~30-50 nodes + relationships
    evidence_rules.yaml       raw evidence → competency mapping
    ladders.yaml              quality ladders (research venue, GPA, internship)
    aliases.yaml              synonyms for messy input
  programs/<program_id>.yaml  demand profile + eligibility rules + provenance
src/unihive/
  models.py        pydantic types: Evidence, StudentProfile, ProgramConfig,
                   Assessment, AuditRecord
  taxonomy.py      load + validate + version the taxonomy
  evidence.py      evidence states, quality/depth/recency/verification
  competency.py    evidence → StudentCompetency levels (deterministic)
  eligibility.py   deterministic rules engine
  scoring.py       readiness = Σ demand × match; bands; confidence
  alternatives.py  the categorical alternative-path rule
  portfolio.py     Safe/Target/Ambitious balancing, 8-12 list
  questions.py     next-best-question (largest current uncertainty)
  report.py        assembles the six-section report *structure* (data only)
  audit.py         AuditRecord construction and replay
  llm/
    extractor.py   resume/free-text → structured evidence
    narrator.py    frozen Assessment → prose
    prompts/       prompt templates as files, not inline strings
cli.py             entry point; must support --score-only (no API key needed)
tests/
```

## The taxonomy is not yours to invent

The competency taxonomy is the ceiling on everything above it and is being
built from observed real student profiles plus expert validation. **Do not
author competency nodes, demand profiles, or evidence-mapping weights from your
own domain knowledge.** Build the schema, loader, validator, and machinery.
Where seed content is needed to make tests run, mark it explicitly:

```yaml
provisional: true          # required until a human validates
validated_by: null
source: null
```

The loader must warn on every `provisional: true` record and the CLI must print
a count of unvalidated configs in use. Never silently promote provisional data.

## Conventions

- Python 3.11+, `pydantic` v2 for all models, `pytest`, `ruff`, `mypy --strict`
  on `src/unihive/` excluding `llm/`.
- Type-annotate everything. No bare `dict` or `Any` in public signatures.
- Enums, never string literals, for states/bands/levels.
- Pure functions in the scoring path — no classes holding mutable state.
- Docstrings state which spec section a function implements, e.g.
  `"""Implements Build Spec §6 — categorical alternative-path rule."""`
- Every scoring function returns its own explanation trace (which competencies
  contributed, how much, from which evidence). Explainability is a return
  value, not a logging side effect.

## Task hygiene

- Work only within the scope of the task given. Do not refactor adjacent
  modules, do not "improve" the scoring formula, do not add features.
- Write tests in the same task as the code they cover.
- Run `pytest` and `ruff check` before finishing. Report failures rather than
  deleting or weakening tests to get green.
- If the task is underspecified, implement the narrowest reasonable reading and
  list your assumptions in the summary. Do not guess at product behaviour that
  the specs don't cover.
