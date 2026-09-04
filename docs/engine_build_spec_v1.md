UniHive · Admissions Intelligence Engine — Build Spec

**UniHive**

**Admissions Intelligence Engine**

Authoritative Build Specification

*Competency-taxonomy-first. Deterministic where it counts. Honest by construction.*

This document supersedes the earlier “Recommendation Engine Spec v0.1.” It reconciles every design decision reached across our working sessions into one source of truth.

Version 1.0 — build reference.  Internal.

# **Contents**

# **0. The whole thing in one page**

We are not building a university-recommendation engine. Those are a commodity — ChatGPT, Yocket, and a dozen others already produce school lists. We are building the thing students are actually stuck on: **an honest read on where their profile stands and exactly what to do next.** The recommendation falls out downstream. The wedge is trusted diagnosis.

The engine that delivers this rests on one foundation: a **shared competency taxonomy.** Evidence maps to competencies; programs declare which competencies they demand and at what level; readiness is the comparison between the two. This single structure is what keeps scoring principled instead of drifting into per-program invented weights — and it is the asset competitors don’t have.

What makes it defensible and un-fakeable by a general chatbot: it is **deterministic where consistency matters** (eligibility, competency matching), it is **honest by construction** (unknown ≠ zero, bands not percentages, everything sourced), and it **simulates its own improvements** (“do X → your readiness moves from Developing to Competitive”). A general model has no deterministic core to simulate against and no verified data behind it.

| **The load-bearing decisions (do not compromise these)** 1) Competency taxonomy is the foundation — build it first, as its own milestone, expert-validated.  2) The score path is deterministic; the LLM sits around it, never inside it.  3) Unknown is never treated as zero.  4) No admission percentages until outcomes exist and the model is calibrated.  5) Six outputs stay separate — never collapse into one number. |
| --- |

# **1. What we are building — and what we’re not**

### **The wedge**

“**Know where you stand. Know what to do next.**” UniHive explains which academic paths fit you, where your profile stands for each specific program, and exactly how to improve before applying. Recommendation is a *result* of that diagnosis, not the headline product.

### **Three separate tasks — do not merge them**

| **Task** | **Question it answers** | **Nature** |
| --- | --- | --- |
| Pathway discovery | Should this student consider CS, DS, AI, Cybersecurity, InfoSys — or something adjacent that fits better? | Exploration + fit |
| Program-specific assessment | How strong is this student for MS X at University Y? Do they meet prerequisites? What evidence is relevant to that exact program? | Deterministic + rubric |
| Portfolio construction | Which programs are Safe / Target / Ambitious? Does the final list satisfy budget, location, funding, career? | Optimization |

These are separate recommendation problems and get implemented separately. The industry-standard **candidate generation → scoring → re-ranking** pattern maps onto them directly.

# **2. Non-negotiable product rules**

Document these now; they are design constraints, not preferences. Every one of them is what protects credibility — the entire game in admissions advice.

### **Unknown is not zero**

Every competency and credential carries exactly one state. Missing information is a gap in knowledge, not a weakness in the student.

| **State** | **Meaning** |
| --- | --- |
| verified_present | Backed by a document (transcript line, publication, dated cert) |
| self_reported_present | Student claims it; no document backs it |
| confirmed_absent | Student explicitly says they have NOT done/studied it |
| unknown | Materials simply don’t mention it — treated as “not yet assessed,” never as a deficit |
| not_applicable | The field doesn’t apply to this student |

### **Eligibility and readiness are separate**

A student can be eligible but weak, strong but ineligible, conditionally eligible, or impossible to assess because information is unknown. These are different axes and must never be blended into a single verdict.

### **No single score represents everything**

Keep six outputs distinct at all times: pathway readiness, program alignment, eligibility, student-preference fit, admissions outlook, and data confidence. A product manager will later want to collapse these into one number for the UI. Don’t.

### **A readiness score is not an admission probability**

No admission percentages until outcomes are sufficient and the model is calibrated. And preference behavior cannot train an admission model — saving a university means “interested,” not “likely to be admitted.” Keep preference labels and outcome labels in separate stores forever.

### **Every assessment is reproducible**

Store, for every assessment: model/rubric version, evidence used, program-data version, what was missing, source links, and confidence. This is both what makes the system auditable and what turns each assessment into future training/eval data.

# **3. The competency taxonomy — the foundation**

This is the core shared language and the project’s single biggest risk: its quality is a **ceiling** on everything above it. A mediocre taxonomy fails silently — the system still emits confident-looking assessments that are subtly wrong. So it is built first, as its own milestone, and validated by a real domain/admissions expert.

### **Scope for v1 (deliberately narrow)**

- Five fields only: Computer Science, Data Science, Artificial Intelligence, Cybersecurity, Information Systems

- US master’s programs only

- Your existing ~35 verified universities

### **What to build**

- ~30–50 competency nodes across the five fields (networking, operating systems, cryptography, statistics, ML, distributed systems, etc.)

- Relationships between competencies

- Evidence-to-competency mapping rules (what raw evidence indicates which competency, and how strongly)

- Program-to-competency demand profiles (see §5)

- Career mappings, and synonyms/aliases for messy inputs

### **Anchor to standards, then refine**

Start from the federal **CIP taxonomy** (the standard classification for fields of study) and connect program fields to occupations via **O*NET** (skills/knowledge/abilities for 900+ occupations). But “Computer Science” is too broad — you still need your own finer competency layer on top. Keep the whole thing **versioned**, never permanently frozen.

| **Build it FROM observation, not the whiteboard** The concierge reviews you’re running now are the empirical input. “Which evidence repeatedly matters” across real profiles tells you which competency nodes are real and which you’d have invented at a desk. Seed v1 of the taxonomy from what you actually see students have and get judged on — then validate with the expert. Don’t freeze it from domain knowledge and check against students afterward; build it the other way round. |
| --- |

# **4. The evidence model: two-level, not flat**

A flat “relevance to field X” score is not enough, because two programs in the *same* field can demand very different things (a technical MS Cybersecurity wants networks/crypto; a policy-oriented one wants governance/risk; a third is really CS with a security concentration). Routing evidence through the shared competency layer solves this cleanly.

### **Step 1 — Map evidence to competencies (program-independent)**

An ML publication → machine learning: high; statistics: moderate; cybersecurity: low. This is a property of the evidence itself, computed once.

### **Step 2 — Each program declares its competency demand profile**

Technical MS Cybersecurity, for example: networking (required/high), operating systems (high), security (high), programming (medium), policy (low). Programs reuse the one taxonomy but specify different expected levels.

### **Step 3 — Compare student evidence against program demand**

**Readiness(s,p) = Σ****k*****  Demand(p,k) × Match( StudentCompetency(s,k), ExpectedLevel(p,k) )***

This is strictly better than inventing an independent weight table per program: the numbers that vary per program are competency demands (which you can source from curricula), not arbitrary global weights. That is what makes the taxonomy genuinely foundational rather than decorative.

### **Each piece of evidence carries five attributes**

| **Attribute** | **What it captures** |
| --- | --- |
| Quality | How strong the evidence is on its own (arXiv preprint vs NeurIPS paper) |
| Relevance (to competency) | Which competencies it speaks to, and how strongly |
| Depth | How deep the demonstrated competence is |
| Verification | Its evidence state (§2) — verified vs self-reported vs unknown |
| Recency | When relevant (a 6-year-old skill vs a current one) |

# **5. Engine architecture (six components)**

The full engine, in the order data flows. Note which parts are deterministic and which are LLM — that boundary is the whole design.

### **5.1 Student Intelligence Profile**

A structured evidence profile, not a resume summary. Stores: academic history + normalized GPA, individual courses/grades, prerequisite competencies, technical & non-technical skills, projects, research (topics/methods/publications/venue quality), work & internships, career goals, subject interests, preferred degree/fields, budget/funding/location constraints, tests & English proficiency, and the evidence source + extraction confidence for every item. Built by the LLM extractor; confirmed/corrected by the student.

### **5.2 Academic ****&**** career ontology**

The relationships: student evidence → competencies → fields → concentrations → degree programs → careers. E.g. Python + statistics + ML research → machine learning & quantitative analysis → DS/AI/CS → Data Scientist / ML Engineer. This is the taxonomy of §3 in active use.

### **5.3 Goal-discovery engine**

Supports three entry modes: (a) “I know what I want to study,” (b) “I know my career goal but not the degree,” (c) “Help me explore using my profile.” Even when a student names a program, run related-path discovery in the background — but surface alternatives only when meaningful (see the categorical rule, §6). Base alternatives on career intention, genuine interest, existing preparation, time to close gaps, and constraints — never on resume similarity alone, and never override the student’s stated choice silently.

### **5.4 Eligibility engine — deterministic**

Not AI-generated. Returns one of: Eligible / Conditionally eligible / Not currently eligible / Eligibility unknown. Rules: required prior degree, minimum GPA, mandatory coursework, English score, GRE requirement, work-experience requirement, citizenship/residency, deadline & intake availability. The LLM may extract these requirements from university pages, but the final check runs on structured rules with source links.

### **5.5 Contextual scoring engine**

Every program gets a **versioned scoring configuration** — its competency demand profile plus dimension emphasis. Illustrative shape for a technical MS Cybersecurity:

| **Dimension** | **Weight** |
| --- | --- |
| Academic & prerequisite match | 30% |
| Security & systems skills | 25% |
| Relevant projects / work | 20% |
| Research alignment | 10% |
| Tests & communication | 10% |
| Supporting evidence quality | 5% |

An MS Data Science config raises math/stats/programming/data; a PhD config heavily raises research agenda, publications, methods, faculty alignment, and recommendations. **Crucially**, these weights are provisional and, until validated against outcomes or an expert, must be treated as educated assumptions — which is exactly why the output is a band, not a precise number, and why no admission percentage is shown.

Outputs stay separated (§2): pathway readiness, program alignment, eligibility, preference fit, admissions outlook, data confidence. Readiness is expressed as a **band — Emerging / Developing / Competitive / Strong** — with a confidence label, never as “80 = 80% chance.”

### **5.6 Recommendation ****&**** portfolio optimizer**

After scoring candidates, re-rank by the student’s priorities: career alignment, academic readiness, affordability, funding likelihood, curriculum, faculty/research, location, outcomes, admissions risk, data confidence. Then construct a balanced list of roughly 8–12 programs — not simply the ten highest scores. Portfolio balance (a spread of Safe/Target/Ambitious that also satisfies constraints) is its own objective.

# **6. When to surface an alternative pathway**

Do **not** use a numeric threshold like “15 points higher” — those points are provisional and inventing a cutoff on them manufactures false precision. Use a **categorical** rule instead. Surface a related path only when ALL of these hold:

- Its current-readiness band is at least one full band higher than the chosen path.

- That difference rests on medium/high-confidence (verified or self-reported) evidence — not on missing information.

- It stays reasonably aligned with the student’s stated interest or career goal.

- The student has not explicitly rejected that field.

- Show at most two alternatives.

Phrasing matters. Say *“your existing evidence is currently stronger for Data Science,”* never *“you should abandon Cybersecurity.”* Preserve agency: present the chosen path’s readiness AND the alternatives with the delta and reasoning, then let the student choose what to optimize for (strongest current fit vs. long-term career alignment vs. show both). Later, once you have data, the band-change threshold can be empirically tuned and versioned.

# **7. Progressive questioning, not a 50-field form**

Ask only questions that could materially change the recommendation — the next question should target the single largest uncertainty in the current assessment. For the cybersecurity example, that might be: why cybersecurity; which role (security engineer / analyst / cloud / governance / research); have you done networking, OS, or security coursework; would you spend 3–6 months bridging into security; do you want strongest current fit or strongest long-term alignment? This is both a better experience and a way to resolve the highest-value unknowns first.

# **8. Build sequence (stage-gated, not date-gated)**

Ordered so each stage ships something usable and de-risks the next. The concierge is Stage 0 and is already running — keep feeding it.

### **Stage 0 — Concierge discovery (in progress now)**

- Observe ~10 students, then build a first prototype, then observe ~10 more (better than 20 up front).

- Produce the profile diagnostic manually via the 3-stage prompt pipeline; log every case in the tracker.

- Record what evidence repeatedly matters (→ seeds the taxonomy) and where the LLM’s judgment feels inconsistent (→ the tripwire for what to make deterministic).

- Watch behavior, not stated approval: do they change program, change list, complete an action, return, refer, pay.

### **Stage 1 — Taxonomy as its own milestone**

- Build the ~30–50 nodes, mappings, and program demand profiles for the five fields (§3).

- Validate against real student profiles, university curricula, and ≥ 1 admissions/domain expert. Version it.

### **Stage 2 — Hybrid MVP**

- LLM extracts structured evidence.

- Student confirms or corrects the extraction.

- Deterministic rules evaluate eligibility.

- Competency matching evaluates readiness (bands + confidence).

- LLM explains the structured result in plain language.

- Related-path discovery surfaces meaningful alternatives (§6).

- Portfolio construction builds the balanced 8–12 list.

- No admission percentages.

### **Stage 3 — Build only where the prototype breaks**

Don’t pre-build. Let observed failures pull each component into existence:

| **Observed failure** | **Component it justifies building** |
| --- | --- |
| Misses mandatory prerequisites | Stronger deterministic eligibility rules |
| Inconsistent answers for the same profile | Versioned scoring / rubric system |
| Can’t compare CS vs Cyber consistently | Competency & program taxonomy refinement |
| Invents university information | Verified program database + retrieval |
| Can’t simulate improvement reliably | Evidence-based readiness model |
| University ordering feels arbitrary | Learning-to-rank ordering model |
| Admission bands poorly calibrated | Outcome-trained, calibrated prediction model |

# **9. The long-term hybrid (where this lands)**

| **Layer** | **Responsibility** | **Deterministic?** |
| --- | --- | --- |
| LLM | Resume extraction, conversation, clarification, explanations | No |
| Rules | Eligibility, deadlines, prerequisites, hard requirements | Yes |
| Rubrics / taxonomy | Profile–program competency alignment | Yes |
| ML (later) | Program ranking; admission-outlook calibration | Learned, then calibrated |
| Human (initially) | Quality control + rubric development | n/a |

The invariant across all of it: the LLM sits *around* the deterministic core, never *inside* the number. That boundary is what keeps the system honest, explainable, auditable — and impossible for a general chatbot to replicate.

# **10. Why this is defensible**

The market is not empty — CollegeVine (undergrad chancing), Yocket (grad finder + admit predictor), Shiksha, GradRight SelectRight, ApplyBoard, Cialfo all do personalized matching. “AI-powered personalized university recommendations” alone will not differentiate anything. The defensible position is the diagnosis wedge plus what accumulates underneath it:

- Structured, state-tagged student evidence

- Program-specific competency demand models (the taxonomy)

- Transparent, sourced explanations

- Longitudinal profile improvement over time

- Student preference & rejection feedback

- Verified application outcomes (the eventual calibration data)

- Better, verified program-level data — depth over inflated breadth

| **The wedge and the incentive moat reinforce each other** Diagnosis is only trustworthy if the diagnostician isn’t conflicted. UniHive’s structural independence from university money is what makes “honest read on your profile” credible — a competitor monetizing university placements or loan origination cannot make that claim stick. So the no-university-money principle isn’t a footnote; it’s the proof that the diagnosis is honest. Lead with it. |
| --- |

Internal · v1.0 · page