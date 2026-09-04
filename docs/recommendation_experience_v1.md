UniHive · The Recommendation Experience

**UniHive**

**The Recommendation Experience**

Onboarding · What Students Get · How Scoring Works

*The product layer: what the student experiences, and how the same engine produces a fair, different read for every profile.*

Companion to the Admissions Intelligence Engine Build Spec (v1). This document is the experience & scoring-logic view; the Build Spec is the technical architecture.

Version 1.0 · Internal / product reference

# **Contents**

# **1. The promise to the student**

Most tools hand a student a list of universities and a number. UniHive does something different and harder: it tells them **where they actually stand, why, and what to do about it.** The recommendation is the end of the story, not the start.

Everything in the experience is built to deliver three things, in this order:

- **Understanding — **“Here’s what we see in your profile, honestly, including what we can’t yet judge.”

- **Direction — **“Here are the 2–3 things that would help you most, and what each one is worth.”

- **Options — **“Here are the programs that fit, balanced across ambition, with the reasons.”

| **The feeling we’re creating** Not “here’s your score, go apply.” That’s a calculator, and ChatGPT can fake it. The feeling is: an honest, knowledgeable advisor who read my whole profile, told me the truth, showed me exactly how to improve, and had no reason to flatter me. Trust is the product; the list is a by-product of trust. |
| --- |

# **2. Onboarding: seed fast, then grow**

Never open with a 50-field form — people abandon it. Onboarding has two phases: a fast seed that produces a first honest (low-confidence) read, then continuous enrichment where the profile — and the recommendation — gets better the more the student shares.

### **Entry: three doors**

The first question routes the student by where they are in their thinking. This is the goal-discovery engine’s three modes, made visible.

| **The student says…** | **We route to** |
| --- | --- |
| “I know what I want to study” | Confirm the program → assess fit → quietly check for better-fitting adjacent paths |
| “I know my career goal, not the degree” | Career → competencies → which degrees/concentrations get them there |
| “Help me explore using my profile” | Extract evidence → surface the fields their profile most supports |

### **Phase 1 — The fast seed (~2–3 min, 8–12 questions)**

Only the highest-information questions — enough to produce a first read. Everything else comes later.

- Target degree + concentration (their stated intent — we validate fit against it, never override it)

- Country + target-tier ambition (“dream” level)

- Most recent degree, field, institution

- GPA + scale

- Graduation year / timeline to apply

- International or domestic (drives English tests, visa, funding paths)

- Budget / funding sensitivity (need funding vs. self-funded)

- Resume upload (the extractor pulls structured evidence from it — not a manual re-type)

- One free-text: “What do you want to do after your MS?” (feeds concentration-fit + narrative)

Then — immediately — show a first read with a **visible confidence band**. The low confidence is the point: it’s honest, and it creates the pull to add more.

| **First read — after the fast seed** |
| --- |
| **Your path: **MS Cybersecurity **Readiness: **Developing  *·  Confidence: Low* We’ve got a solid start, but there’s a lot we don’t know yet. **Add 3 more things and this read gets much sharper:** • Your coursework / transcript • Any projects or internships • Your target school list |

### **Phase 2 — Progressive enrichment (never “done”)**

After the seed, the system asks only for the **next thing that would most change the assessment** — the largest current uncertainty — not a fixed checklist. Each addition visibly moves the read and tightens confidence. This is the growth loop: add evidence → confidence rises, score sharpens → new highest-value gap surfaces → student acts.

Progressive questions are targeted. For the cybersecurity case: why cybersecurity; which role (engineer / analyst / cloud / governance / research); have you done networking, OS, or security coursework; would you spend 3–6 months bridging; do you want strongest *current* fit or strongest *long-term* career alignment?

# **3. What the student actually gets**

The output is a structured report, not a number. Six parts, always in the same shape so it feels reliable and comparable over time.

| **Section** | **What it tells the student** |
| --- | --- |
| What we understand about you | The evidence we extracted, and — critically — what we don’t yet know (marked as ‘not assessed,’ not ‘weak’) |
| Your strengths | Specific strong evidence, each tied to what it demonstrates |
| Your gaps | Confirmed gaps (not unknowns), why each matters for the target, and what to do |
| Your chosen path + alternatives | Readiness band for what they picked, plus any path their evidence currently fits better |
| Top 3 actions | Ranked by impact-per-effort, each with what it would move |
| What we can’t assess yet | Named honestly, with what to provide to unlock it |

### **The chosen-path + alternatives view (the signature moment)**

This is where UniHive is unmistakably different. We honor the student’s choice AND show them the truth, without ever saying “abandon your goal.”

| **Your path assessment** |
| --- |
| **Your selected path: MS Cybersecurity** Current readiness: Developing*   · Confidence: Medium* You have a strong general computing foundation, but we found limited evidence in networking, operating systems, and security-specific work. **Paths your current evidence fits well right now:** • MS Data Science — Strong *(high confidence)* • MS Computer Science — Competitive *(high confidence)* • MS Cybersecurity — Developing *(medium confidence)* You can absolutely continue with Cybersecurity. A security project, a networking course, and Security+ would materially raise your readiness. **What should we optimize for?** [ My cybersecurity career ]   [ My strongest profile today ]   [ Show both ] |

That last question is the whole philosophy in one interaction: **intelligent guidance that preserves agency.** We never decide for them; we make the trade-off visible and let them choose.

### **The action plan (why it beats generic advice)**

Because the engine can simulate its own score, each suggested action comes with **what it would move** — not “you should publish more” but “your research evidence is at the preprint level; a workshop acceptance would lift it toward Competitive for research-track programs.” Actions are ranked by *impact-per-effort*: a fast profile addition and a slow publication are both shown, with honest effort labels, so the student can pick based on the time they have.

# **4. How we score different profiles — fairly and differently**

The core principle: **two students should never get the same read unless their work is genuinely equivalent for that specific program — and the same student should get different reads across programs.** Here is how the engine achieves that. (Full formulas live in the Build Spec; this is the plain-language logic.)

### **Principle 1 — Evidence is graded by level of work, not counted**

A dimension isn’t worth flat points; it has a ceiling and a quality ladder. Two students with “a publication” each get different points based on what the publication actually is.

| **Research evidence** | **Roughly earns** |
| --- | --- |
| arXiv preprint (not peer-reviewed) | Low |
| Workshop paper at a real venue | Moderate |
| Peer-reviewed conference (mid-tier) | High |
| Top-tier venue (NeurIPS / CVPR / ACL) | Very high |

First-author vs. co-author is a further modifier. **One strong paper can and should outscore two weak ones.** The same laddering applies to GPA (graded with institution rigor and trend), internships, and LORs (a known researcher who supervised real work > a generic reference).

### **Principle 2 — The same evidence counts differently per program**

Evidence maps to competencies; each program demands different competencies at different levels. So a piece of evidence is worth a lot for one program and little for another — without us inventing arbitrary per-program weights.

| **Student evidence** | **MS Data Science** | **MS CS** | **MS Cybersecurity** |
| --- | --- | --- | --- |
| ML research publication | Very high | High | Low |
| Python + statistics | Very high | High | Moderate |
| Networking course | Low | Moderate | Very high |
| Security internship | Low | Moderate | Very high |
| Operating systems | Moderate | High | Very high |

The consequence: the **same two students can flip ranking** depending on the program. A strong-research / lighter-GPA student ranks higher for a research-track program; a strong-projects / higher-GPA student ranks higher for a professional MS. That’s not inconsistency — it’s the engine being honest about *fit*.

### **Principle 3 — Profile shape matters (not just totals)**

A profile that’s coherent for the target beats a flat one with the same total. Two safeguards, both explainable: floors (if a program has a hard prerequisite the student lacks, that’s flagged, not silently averaged away) and coherence (a clearly research-shaped profile applying to a research program reads as a stronger, more credible candidate). We keep these rules few and each defensible in one sentence — never a black box of hidden adjustments.

### **Principle 4 — Missing information is never counted as weakness**

If we don’t know whether a student has studied networking, that is **unknown**, shown as “not yet assessed,” never as a zero or a weakness. Only something the student confirms they haven’t done, or clearly weak evidence, counts as a real gap. This is what keeps a half-built profile from getting an unfairly harsh read — and it’s a large part of why students trust the output.

### **Principle 5 — Honesty about certainty**

Every read carries a confidence label (high / medium / low) based on how much evidence is verified vs. unknown. Thin data → a wider, more cautious read and a visible low-confidence flag. And we never convert a readiness band into an admission percentage — “Strong” does not mean “80% chance.” We show **bands with the evidence behind them**, because a made-up number is the fastest way to lose the trust the whole product depends on.

### **Two profiles, side by side**

The same engine, two students, one target (a research-oriented MS). Note how the reads differ — and how neither is punished for what’s merely unknown.

|  | **Student A** | **Student B** |
| --- | --- | --- |
| GPA | 3.9, grade-inflated program | 3.4, rigorous program |
| Research | None stated (unknown) | 2 workshop papers, first author (verified) |
| Projects | Several strong industry projects | One class project |
| Read for a RESEARCH program | Competitive, but research evidence not yet assessed — the key unknown to resolve | Strong — research shape fits the target well |
| Read for a PROFESSIONAL MS | Strong — project shape fits | Competitive — lighter on applied project work |
| Top action | “Tell us about any research — it’s the biggest unknown holding your read back” | “Add an applied project to round out a research-heavy profile” |

# **5. How the recommendation improves over time**

The profile is a living thing, not a one-time form. Every interaction makes the recommendation better, and the student sees it happen.

- **Student adds evidence **(a course, a project, a paper, a confirmed ‘no I haven’t done X’).

- **Confidence rises and the read sharpens **— the band may move; the uncertainty narrows.

- **The engine recomputes gaps **and surfaces the next highest-impact-per-effort action.

- **As deadlines approach, priorities shift **from slow high-impact moves to fast wins (timeline-aware nudging).

- **The school list updates **as readiness changes — programs move between Safe / Target / Ambitious with the reasons shown.

| **What the student remembers** “It actually got smarter as I used it, and it told me the truth even when the truth wasn’t flattering.” That memory is what earns the referral, the return visit, and eventually the payment — and it’s something a static list or a generic chatbot can’t manufacture. |
| --- |

# **6. What we deliberately don’t do**

- **No admission percentages.** Bands with evidence, never “73% chance,” until we have real outcomes and a calibrated model.

- **No silent overrides.** We never swap a student’s chosen path for them; we show alternatives and let them choose.

- **No invented facts.** If it isn’t in the evidence, it’s unknown — we don’t guess a skill from an adjacent one.

- **No punishing the unknown.** Missing information lowers confidence, not the student’s standing.

- **No pay-to-rank.** No university pays to appear or rank higher — ever. This is what makes an honest read believable: the advisor has no reason to flatter or steer. The independence is the proof the diagnosis is trustworthy.

Internal · v1.0 · page