# PRD — Product Requirements Document

**Varsity Ad Engine — Autonomous Ad Generation System for Varsity Tutors**

| Project | Client | Scope | Deadline |
| --- | --- | --- | --- |
| Nerdy / Gauntlet | Varsity Tutors (SAT Prep) | v1 (text) + v2 (images) | Thursday |

---

## 1. Objective & Mission

> **Mission Statement**
>
> Build an autonomous, self-improving Facebook and Instagram ad generation engine for Varsity Tutors that reliably distinguishes excellent copy from mediocre copy, enforces a strict 7.0/10 quality threshold, generates companion ad creative images, and tracks performance-per-token ROI — with minimal human intervention and measurable quality improvement across 3+ iteration cycles.

---

## 2. Key Features & Evaluation Impact

| Feature | Description | Evaluation Impact |
| --- | --- | --- |
| Multi-Model Pipeline | Gemini Flash drafts. Gemini Pro judges. Different capability tiers for different jobs. | Bonus: Multi-model orchestration (+3) |
| 5-Dimension Evaluator | Every ad scored 1–10 on Clarity, Value Prop, CTA, Brand Voice, Emotional Resonance with written rationale. | 25% of grade — Quality Measurement |
| Self-Healing Loop | Identifies weakest dimension. Regenerates targeting only that weakness. Max 3 cycles. | 20% of grade — Iteration & Improvement |
| Competitive Intelligence | Princeton Review, Khan Academy, Kaplan, Chegg patterns injected into every generation prompt. | Bonus: Competitive Intelligence (+10) |
| Quality Trend Chart | Matplotlib chart showing average score rising across 3+ iteration cycles. | Bonus: Quality trend visualization (+2) |
| v2 Image Generation | Companion ad creative per passing ad via Imagen / Nano Banana. | Scope v2 — key differentiator |
| Performance-per-Token | Cost per publishable ad tracked. ROI documented in decision log. | Bonus: Perf-per-token tracking (+2) |
| Failure Handling | After 3 cycles: `status = unresolvable`, logged, auto-continue. No human needed. | 20% of grade — System Design |

---

## 3. Core Workflow

```
INPUT: briefs.json + competitive_context.json + brand_guidelines.json

FOR each brief:
  [Gemini 1.5 Flash]  ->  Generate Ad (primary_text, headline, description, cta_button)
                          |
  [Gemini 1.5 Pro]   ->  Score 5 dimensions (1-10) + rationale JSON
                          |
                    average_score >= 7.0?
                    YES  ->  Save to ads_library.json
                         ->  [Imagen] Generate companion image
                         ->  Log tokens + cost + cycle count
                    NO   ->  Identify weakest_dimension (returned by judge)
                         ->  Build targeted regeneration prompt
                         ->  cycle_count += 1
                         ->  cycle_count <= 3?  REPEAT from generation step
                         ->  cycle_count >  3?  status = unresolvable
                                                log failure_reason + all scores
                                                CONTINUE to next brief

OUTPUT: ads_library.json + iteration_log.csv + quality_trends.png
```

---

## 4. 5-Dimension Evaluation Framework

| Dimension | Score 10 — Excellent | Score 1 — Fail | Feedback Loop Trigger |
| --- | --- | --- | --- |
| Clarity | Crystal clear single takeaway under 3 seconds | Confusing, competing messages everywhere | Simplify hook, reduce copy length, one message only |
| Value Proposition | Specific differentiated benefit (200+ point improvement) | Generic feature list ("we have tutors") | Add specific outcome numbers + Varsity differentiator |
| Call to Action | Specific, urgent, low-friction ("Start free assessment") | No CTA or buried and vague | Rewrite CTA to match funnel stage, add urgency word |
| Brand Voice | Distinctly empowering, knowledgeable, approachable | Generic — could be any tutoring brand | Rewrite with Varsity voice markers and outcome focus |
| Emotional Resonance | Taps directly into parent anxiety or student ambition | Flat, purely transactional copy | Add emotional hook — fear, hope, relief, or aspiration |

> **Quality Threshold Enforcement**
>
> - Publishable threshold: **7.0 / 10** average across all 5 dimensions
> - Target for Excellent grade bracket: **7.5+** average across all 50+ ads
> - Every ad must have machine-generated rationale for each score — 100% explainability
> - `passes_threshold` boolean + `weakest_dimension` field returned by judge drives feedback loop automatically

### Calibration Anchors — Hardcoded in `rubrics.py`

The following gold and poor anchor examples must be hardcoded directly into `rubrics.py` — not generated dynamically. They give the Judge a permanent, stable reference for what a 10 and a 1 look like, ensuring consistent scoring across all 50+ ads.

**GOLD ANCHOR — Score 8–10**

```
primary_text: Is your child's SAT score standing between them and their dream school?
              Students working with a top-matched Varsity Tutors expert improve an average of 200+ points.
              Unlike one-size-fits-all courses, we match your child with a tutor in the top 5% —
              based on their exact weak areas. Over 3.4 million learner sessions rated. Start free.
headline:     Your Child's Score Can Improve 200+ Points
description:  Matched with a top 5% tutor in 24 hours. Results, not just prep hours.
cta_button:   Start Free Assessment
```

> WHY IT SCORES HIGH: Specific fear hook + stat + clear differentiator (1-on-1 matching) + social proof (3.4M ratings) + low-friction CTA + outcome-first voice throughout

**POOR ANCHOR — Score 1–4**

```
primary_text: Varsity Tutors offers SAT tutoring services. We have experienced tutors
              who can help your student prepare for the SAT exam. Sign up today.
headline:     SAT Tutoring Available Now
description:  Contact us to learn more about our tutoring options.
cta_button:   Learn More
```

> WHY IT SCORES LOW: Generic feature-first copy with no hook, no specific outcomes, no social proof, no differentiation from any competitor, no emotional angle, weak CTA

---

## 5. Iteration & Failure Handling

| Cycle | Action | Log Entry |
| --- | --- | --- |
| Cycle 1 | Initial generation from brief + competitive context | `cycle: 1, scores: {...}, avg: X.X` |
| Cycle 2 | Targeted regeneration: fix `weakest_dimension` only | `cycle: 2, weakest: value_proposition, improved: +1.2` |
| Cycle 3 | Second targeted regeneration if still below 7.0 | `cycle: 3, weakest: emotional_resonance, improved: +0.8` |
| Unresolvable | After 3 cycles: flag + log + auto-continue | `status: unresolvable, reason: failed 3 cycles, brief_id: XXX` |

Max 3 cycles before giving up. This prevents infinite loops while allowing enough attempts to demonstrate measurable improvement. The `unresolvable` status provides honest documentation of system limitations — which the rubric rewards.

### Context Window Management in the Loop

**Critical:** when `controller.py` triggers a regeneration, do NOT feed the entire history of failed prompts back to the Drafter. This bloats the context, increases cost, and confuses the model with irrelevant failures.

| What to Feed Back on Each Regeneration Cycle |
| --- |
| **INCLUDE:** The original brief (audience, goal, tone, hook_type) |
| **INCLUDE:** The latest failed ad copy (primary_text, headline, description, cta_button) |
| **INCLUDE:** The specific rationale for the `weakest_dimension` only — one sentence from the judge |
| **INCLUDE:** The targeted instruction: *"Rewrite ONLY the [weakest_dimension]. Keep all other components."* |
| **EXCLUDE:** All previous cycle prompts and responses |
| **EXCLUDE:** Rationale for dimensions that already passed |
| **EXCLUDE:** The full iteration history |
| **RESULT:** Focused regeneration prompt stays under 1,000 tokens per cycle. Cost stays near zero. |

---

## 6. Finalized System Prompts

### Drafter Prompt — Gemini 1.5 Flash

```
You are an elite direct-response copywriter for Varsity Tutors (a Nerdy business).
Generate high-converting Facebook and Instagram ad copy.

BRAND VOICE: Empowering, knowledgeable, approachable, results-focused.
Lead with outcomes, not features. Confident but not arrogant. Expert but not elitist.

AD ANATOMY — generate ALL five components:
1. primary_text: Main copy. Scroll-stopping hook in FIRST LINE.
   Use one of: Question | Stat | Story | Fear | Empathy hook
2. headline: 5-8 words max. Benefit-driven.
3. description: One sentence max. Secondary reinforcement.
4. cta_button: Learn More (awareness) | Sign Up / Start Free Assessment (conversion)
5. image_prompt: A specific, visual UGC-style image generation prompt aligned to the ad.
   Format: [Subject] + [Setting] + [Emotion] + [Brand signal] + [Style: authentic/UGC]
   Example: Parent and teen at kitchen table, teen smiling at laptop showing SAT results,
            relief and pride visible, Varsity Tutors brand colors subtly present,
            authentic UGC style, warm natural lighting, not stock photo

RULES:
- Specific numbers over vague claims: "200+ point improvement" not "better scores"
- Lead with outcomes, never features
- No PII in generated content
- image_prompt must enable UGC-style creative — no polished studio look

COMPETITIVE INTELLIGENCE: {competitive_context}
AD BRIEF: {brief}

RESPOND ONLY with valid JSON:
{"primary_text":"...","headline":"...","description":"...","cta_button":"...","image_prompt":"..."}
```

### Judge Prompt — Gemini 1.5 Pro

```
You are a rigorous Marketing QA Judge for Varsity Tutors. Most ads fail.
Ruthlessly filter mediocre content. Publishable bar: 7.0/10 average.

SCORE each dimension 1-10:
clarity             | 10=clear in <3s  | 7=mostly clear | 4=re-reading needed | 1=confusing
value_proposition   | 10=specific outcome | 7=decent | 4=generic | 1=feature-only
call_to_action      | 10=specific+urgent | 7=clear | 4=vague | 1=missing
brand_voice         | 10=distinctly VT | 7=on-brand | 4=neutral | 1=generic
emotional_resonance | 10=real motivation | 7=some | 4=rational | 1=flat

CALIBRATION:
Gold (8-10): specific outcome hook + social proof + urgent CTA + empathetic tone
Poor (1-4):  "We have SAT tutors. Sign up today. Call us."

RESPOND ONLY with valid JSON:
{
  "clarity":             {"score": X, "rationale": "..."},
  "value_proposition":   {"score": X, "rationale": "..."},
  "call_to_action":      {"score": X, "rationale": "..."},
  "brand_voice":         {"score": X, "rationale": "..."},
  "emotional_resonance": {"score": X, "rationale": "..."},
  "average_score": X.X,
  "weakest_dimension": "...",
  "passes_threshold": true,
  "confidence": "high"
}
```

---

## 7. Repository Structure

```
varsity-ad-engine/
│
├── generate/                   # Drafter agent
│   ├── __init__.py
│   ├── drafter.py              # Gemini Flash + fallback logic
│   └── prompts.py              # System prompts + brief injection
│
├── evaluate/                   # Judge agent
│   ├── __init__.py
│   ├── judge.py                # Gemini Pro 5-dimension scoring
│   └── rubrics.py              # Scoring criteria + calibration anchors
│
├── iterate/                    # Feedback loop controller
│   ├── __init__.py
│   └── controller.py           # 3-cycle limit + unresolvable logic
│
├── images/                     # v2 image generation
│   ├── __init__.py
│   └── image_generator.py      # Imagen / Nano Banana calls
│
├── output/                     # All logs + reports
│   ├── ads_library.json        # 50+ passing ads with all scores
│   ├── iteration_log.csv       # Cycle-by-cycle score tracking
│   └── quality_trends.png      # Matplotlib improvement chart
│
├── data/
│   ├── briefs.json             # 10+ ad briefs (audience, goal, tone, hook_type)
│   ├── competitive_context.json  # Meta Ad Library insights
│   └── brand_guidelines.json   # Varsity Tutors voice rules
│
├── docs/
│   └── DECISION_LOG.md         # YOUR thinking — WHY, failures, limits
│
├── tests/
│   ├── test_generator.py
│   ├── test_evaluator.py
│   ├── test_iteration_cap.py
│   └── test_integration.py
│
├── .env                        # API keys (NEVER commit)
├── main.py                     # One-command entry point
├── requirements.txt
└── README.md
```

---

## 8. `requirements.txt`

```
# AI Framework & APIs
google-generativeai>=0.8.0      # Gemini Flash + Pro + Imagen — one SDK
python-dotenv>=1.0.0            # Secure API key management

# Data & Structured Output
pydantic>=2.0.0                 # Enforce strict JSON schemas from LLM output
pandas>=2.0.0                   # Evaluation reports + CSV exports

# Visualization
matplotlib>=3.7.0               # Quality trend charts (bonus points)
seaborn>=0.12.0                 # Polished chart styling

# Resilience
tenacity>=8.2.0                 # Retry on rate limits — critical for demo stability

# CLI Output
rich>=13.0.0                    # Live pipeline visibility for demo video

# Testing
pytest>=7.4.0
pytest-mock>=3.11.0             # Mock API calls — all tests run offline
```

---

## 9. Data Schemas

### `briefs.json` — Input Schema

```json
{
  "briefs": [
    {
      "id": "brief_001",
      "audience": "Parents of 11th graders anxious about college admissions",
      "product": "SAT 1-on-1 tutoring with free diagnostic assessment",
      "goal": "conversion",
      "tone": "empathetic and urgent",
      "hook_type": "fear"
    },
    {
      "id": "brief_002",
      "audience": "High school students stressed about upcoming SAT",
      "product": "SAT prep course with score improvement guarantee",
      "goal": "awareness",
      "tone": "empowering and peer-level",
      "hook_type": "stat"
    }
  ]
}
```

### `ads_library.json` — Output Schema

```json
{
  "ads": [
    {
      "ad_id": "ad_001",
      "brief_id": "brief_001",
      "cycle": 2,
      "status": "published",
      "ad_copy": {
        "primary_text": "Your child has 3 months...",
        "headline": "Raise Your SAT Score 200+ Points",
        "description": "Matched with a top 5% tutor in 24 hours.",
        "cta_button": "Start Free Assessment",
        "image_prompt": "Parent and teen at kitchen table, teen smiling at laptop showing SAT score improvement, relief and pride on parent face, Varsity Tutors brand colors subtly present, authentic UGC style, warm natural kitchen lighting, not stock photo"
      },
      "scores": {
        "clarity":           { "score": 8, "rationale": "..." },
        "value_proposition": { "score": 9, "rationale": "..." },
        "average_score": 8.2,
        "passes_threshold": true,
        "confidence": "high"
      },
      "image_url": "output/images/ad_001.png",
      "tokens_used": 2847,
      "cost_usd": 0.0043
    }
  ]
}
```

---

## 10. Test Coverage Plan

| # | Test | File | What It Verifies |
| --- | --- | --- | --- |
| 1 | `test_gold_ad_scores_high` | `test_evaluator.py` | Gold standard ad scores >= 8.0 |
| 2 | `test_poor_ad_scores_low` | `test_evaluator.py` | Poor ad scores <= 4.0 |
| 3 | `test_threshold_triggers_regen` | `test_evaluator.py` | Score < 7.0 triggers regeneration |
| 4 | `test_weakest_dimension_identified` | `test_evaluator.py` | Correct weakest dimension returned |
| 5 | `test_iteration_cap_at_3` | `test_iteration_cap.py` | Loop stops after 3 cycles exactly |
| 6 | `test_unresolvable_status_set` | `test_iteration_cap.py` | `status = unresolvable` after 3 failures |
| 7 | `test_json_output_schema` | `test_generator.py` | Output matches pydantic ad schema |
| 8 | `test_csv_export_completeness` | `test_generator.py` | All 50+ ads have scores in CSV |
| 9 | `test_seed_determinism` | `test_generator.py` | Same brief + seed = same output |
| 10 | `test_fallback_activates` | `test_generator.py` | Gemini 2.5 Flash fires on rate limit |
| 11 | `test_image_url_returned` | `test_generator.py` | Image URL present per passing ad |
| 12 | `test_end_to_end_pipeline` | `test_integration.py` | Full brief → publishable ad flow works |

---

## 11. Grade Targets & Scoring Strategy

| Evaluation Area | Weight | Our Target | How We Hit It |
| --- | --- | --- | --- |
| Quality Measurement & Evaluation | 25% | 23–25 pts | 5 dimensions + rationale + calibration + confidence + threshold |
| System Design & Architecture | 20% | 18–20 pts | Modular folders, failure detection, 12 tests, deterministic seeds |
| Iteration & Improvement | 20% | 18–20 pts | 3+ cycles, score gains documented, weakest-dimension targeting |
| Speed of Optimization | 15% | 14–15 pts | Batch generation, minimal human input, smart Flash vs Pro usage |
| Documentation & Thinking | 20% | 18–20 pts | Decision log with WHY, honest failures, competitive intelligence |
| Bonus Points | up to +10 | ~+10 target | Competitive intel (+10), multi-model (+3), trend chart (+2), perf-token (+2) |

> **Automatic Deductions — Must Avoid**
>
> | Risk | Penalty |
> | --- | --- |
> | No working demo | -10 pts |
> | Cannot run with provided instructions | -10 pts |
> | Fewer than 50 ads generated | -5 pts |
> | No evaluation scores on ads | **-15 pts ← BIGGEST RISK** |
> | No iteration or improvement attempted | -10 pts |
> | No decision log | -10 pts |

---

## 12. Sprint Timeline

| Day | Goal | Key Deliverable | Done When |
| --- | --- | --- | --- |
| Sunday | Foundation | Evaluator calibrated against gold and poor ads | Judge scores gold >= 8.0, poor <= 4.0 |
| Monday | Core Pipeline | Generator + Judge + basic loop working end-to-end | One brief produces a scored ad |
| Tuesday | Self-Healing Loop | 50+ ads generated and scored | `ads_library.json` has 50+ passing entries |
| Wednesday | v2 + Polish | Images + quality trend chart + decision log written | `quality_trends.png` shows upward slope |
| Thursday | Submission | README + tests + demo video recorded | One-command setup works from cold start |

---

## 13. Decision Log Outline

The decision log is **20% of the grade**. It must show YOUR thinking — not just what was built. Key decisions to document:

- Why Gemini Flash for drafting and Gemini Pro for judging — speed vs quality tradeoff
- Why 5 dimensions and not more or fewer — decomposition rationale
- Why 7.0/10 threshold — what reasoning supports this bar
- Why max 3 iteration cycles — what happens if you allow infinite loops
- How competitive intelligence was gathered — Meta Ad Library methodology
- What **failed** — ads that never passed, prompts that produced garbage, hard-to-improve dimensions
- Performance-per-token findings — average cycles to 7.0+, cost per publishable ad
- Limitations — what the system cannot do, edge cases, known weaknesses

> **Decision Log Golden Rule**
>
> The decision log separates candidates who **THINK** from candidates who **PROMPT**.
>
> Every major choice needs a **WHY**, not just a WHAT.
>
> Honest failures are worth more than polished successes with no explanation.
>
> Write it as you build — not all at the end.

---

*End of Product Requirements Document | Varsity Ad Engine | Nerdy / Gauntlet 2026*
