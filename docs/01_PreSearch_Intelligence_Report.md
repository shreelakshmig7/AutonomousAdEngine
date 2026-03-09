# PRE-SEARCH Intelligence Report

**Varsity Ad Engine — Autonomous Ad Generation System for Varsity Tutors**

| Project | Brand | Platform | Deadline |
| --- | --- | --- | --- |
| Nerdy / Gauntlet | Varsity Tutors (SAT Prep) | Facebook & Instagram | Thursday |

---

## 1. Domain & Constraint Definition

All constraints were locked before any architecture or code decisions were made.

| Constraint | Decision | Rationale |
| --- | --- | --- |
| Domain | Facebook & Instagram paid ads only | One channel family, done well — per project spec |
| Brand | Varsity Tutors (Nerdy) | SAT prep focus, empowering voice, results-oriented |
| Primary Audience | Parents of 11th/12th graders + SAT students | Highest intent, highest anxiety, highest lifetime value |
| Ad Volume | 50+ ads minimum | Hard requirement — missing triggers automatic -5 pt deduction |
| Quality Threshold | 7.0 / 10 average across 5 dimensions | Non-negotiable floor, autonomously enforced |
| Human-in-the-Loop | Minimal — fully autonomous self-healing | System detects and fixes its own failures |
| Iteration Cap | Max 3 cycles per brief | Prevents infinite loops — unresolvable logged after failure |
| PII Policy | Zero PII in any generated content | Hard constraint from project specification |
| Reproducibility | Deterministic seeds on all generation calls | Required for testing and submission verification |

---

## 2. Competitive Intelligence — Meta Ad Library Research

Research conducted via the Meta Ad Library on all four primary competitors. Patterns are injected directly into the Drafter prompt via `competitive_context.json`.

### 2.1 Competitor Ad Pattern Analysis

| Competitor | Dominant Hook | Top CTA | Emotional Angle | What to Steal |
| --- | --- | --- | --- | --- |
| Princeton Review | Stat: Students score 200+ pts higher | Start free practice test | Parent fear to measurable relief | Specific score numbers + test date urgency |
| Khan Academy | Empathy: Free, official SAT prep | Practice for free | Accessibility + zero pressure, College Board trusted | Approachable tone, free-first funnel |
| Kaplan | Authority: Trusted by millions since 1938 | Get free practice test | Legacy trust + score-back guarantee | Guarantee framing, credibility signals |
| Chegg | Value: Expert tutors, affordable rates | Try for free | Budget-conscious families, no commitment | Free trial entry, low-friction first CTA |

> **Varsity Tutors Competitive White Space**
>
> Princeton Review owns score guarantees. Khan Academy owns free. Kaplan owns legacy trust.
>
> Varsity Tutors defensible position: **1-on-1 personalization + top 5% vetted tutors + 3.4M learner ratings.**
>
> Every generated ad must lean into personal matching outcomes — never generic *"we have tutors"* copy.
>
> Key differentiators to surface: matched in 24 hrs, top 5% tutors, 3.4M session ratings, outcome-focused.

### 2.2 Proven Body Copy Patterns

| Pattern | Structure | Best For |
| --- | --- | --- |
| PASTA | Problem + Agitate + Solution + Proof + CTA | Conversion campaigns, anxious parents |
| TSC | Testimonial + Benefit + CTA | Social proof awareness ads |
| SOC | Stat + Context + Offer + CTA | Data-driven student segments |
| Fear-Relief | Fear hook + Empathize + Solution + Urgency CTA | High-anxiety parent segments near test dates |

### 2.3 Scroll-Stopping Hook Archetypes

All 5 hook types enforced in the Drafter prompt via the `hook_type` field in `briefs.json`:

- **Question:** Is your child's SAT score holding them back from their dream school?
- **Stat:** Students who prep with a 1-on-1 tutor score 200+ points higher on average.
- **Story:** My daughter went from a 1050 to a 1400 in 8 weeks with Varsity Tutors.
- **Fear:** The SAT is 3 months away. Most students who do not prep wish they had.
- **Empathy:** SAT prep does not have to feel overwhelming. We make it personal.

---

## 3. Meta Ad Performance Benchmarks

Data from Meta IQ 2025, LeadEnforce education reports, and edtech creative performance research.

| Finding | Data Point | Implication for System |
| --- | --- | --- |
| Education ad spend | $2.8B on Meta in 2024, up 12% YoY (eMarketer) | Intense competition — quality filtering is critical |
| Video vs image CTR | Short-form video earns 1.7x higher CTR in education | v2 image generation adds measurable differentiation |
| Specific numbers | Specific metrics outperform vague claims by ~34% | Drafter enforces numbers over adjectives always |
| Social proof impact | Ratings and reviews consistently outperform plain claims | Varsity 3.4M learner ratings must appear in ads |
| Free trial CTA | Free first step outperforms paid commitment by 2.3x | CTAs default to *Start Free Assessment* for conversion |
| UGC-style creative | UGC outperforms polished studio creative for awareness | Image prompts should request authentic real-person look |
| Lookalike audiences | Lookalikes produce 27% lower CPA avg (Meta 2024) | Context for decision log — audience targeting reference |

---

## 4. Technology Stack Research & Final Decisions

All model choices were researched against cost, reliability, and project requirements before being locked in.

### 4.1 Final Locked Tech Stack

| Role | Model | Justification | Est. Cost / 50 Ads |
| --- | --- | --- | --- |
| Drafter | Gemini 1.5 Flash | Fastest Gemini model. Free tier available. Distilled from 1.5 Pro — quality at speed. Built for structured JSON output. | ~$0.00 free tier |
| Judge | Gemini 1.5 Pro | Most capable evaluator in stack. 2M token context. Reliable structured scoring. Validated as LLM judge in benchmarks. | ~$0.02 paid tier |
| Images (v2) | Imagen / Nano Banana | Project Starter Kit recommended stack. Brand-consistent creative generation for v2 scope. | ~$0.04 per image |
| Fallback | Gemini 2.5 Flash or Pro | Same `google-generativeai` SDK. Same API key. Zero new credentials. Auto-activates via tenacity on rate limit. | Pay-as-you-go |

> **Why One Ecosystem — All Gemini**
>
> - **Single API key:** No juggling OpenAI + Anthropic + Google credentials during a Thursday deadline sprint
> - **Single SDK:** `google-generativeai` handles Flash, Pro, Imagen, and fallback in one import
> - **Clean decision log story:** Flash for speed, Pro for quality, 2.5 as fallback — tight and defensible
> - **Cost simplicity:** One billing account, one dashboard, transparent per-token cost tracking
>
> This decision is documented in full in `docs/DECISION_LOG.md`

### 4.2 Full Pricing Comparison — All Options Considered

| Provider | Model | Input per 1M | Output per 1M | Free Tier? | Status |
| --- | --- | --- | --- | --- | --- |
| Google | Gemini 1.5 Flash | $0.075 | $0.30 | Yes | **SELECTED — Drafter** |
| Google | Gemini 1.5 Pro | $1.25 | $5.00 | Yes (limited) | **SELECTED — Judge** |
| Google | Gemini 2.5 Flash | $0.30 | $2.50 | Yes | **SELECTED — Fallback** |
| Google | Gemini 2.5 Pro | $1.25 | $10.00 | No | Available fallback judge |
| OpenAI | GPT-4o-mini | $0.15 | $0.60 | No | Rejected — different provider |
| OpenAI | GPT-4o | $2.50 | $10.00 | No | Rejected — different provider |
| Anthropic | Claude Haiku 4.5 | $1.00 | $5.00 | No | Rejected — different provider |
| Anthropic | Claude Sonnet 4.5 | $3.00 | $15.00 | No | Rejected — different provider |

> **Total Project Cost Estimate**
>
> - 50 ads × ~2,400 tokens each = ~120,000 total tokens across all API calls
> - Gemini Flash drafting: **FREE** on free tier — $0.00
> - Gemini Pro judging: ~$0.02 total for 50 ads on paid tier
> - Image generation v2: ~$2.00 for 50 images at $0.04 each
> - **TOTAL ESTIMATED PROJECT COST: Under $3.00 for the entire build**
>
> Performance-per-token ROI is extremely high — document this in the decision log.

### 4.3 LLM-as-Judge Reliability Research

Judge Reliability Harness 2025 benchmarks validate Gemini 1.5 Pro as primary judge:

| Model | Reliability Score | Structured Output | Role in Stack |
| --- | --- | --- | --- |
| GPT-4o | 90.6% | Excellent | Not used — different provider ecosystem |
| Gemini 2.5 Pro | 87.5% | Excellent | Available as upgraded fallback judge |
| Gemini 1.5 Pro | ~85% | Very Good | **PRIMARY JUDGE — main evaluator** |
| Gemini 1.5 Flash | ~75% | Good | **PRIMARY DRAFTER — generation only** |

---

## 5. Pre-Search Checklist — All Items Complete

### Phase 1: Constraints

- Domain locked: Facebook & Instagram paid social ads only
- Brand locked: Varsity Tutors SAT prep, empowering voice, results-focused
- Scale defined: 50+ ads, 7.0/10 threshold, max 3 iteration cycles
- Human-in-loop minimized: fully autonomous with unresolvable fallback path

### Phase 2: Architecture

- Agent framework: Custom Python pipeline — full control, maximum explainability
- LLM selection: Gemini Flash drafter + Gemini Pro judge — single ecosystem
- Tools: `google-generativeai`, `pydantic`, `pandas`, `matplotlib`, `seaborn`, `tenacity`, `rich`, `pytest`, `pytest-mock`
- Observability: 5-dimension scoring + `iteration_log.csv` + `quality_trends.png` chart

### Phase 3: Risks Mitigated

- Rate limits: tenacity exponential backoff + Gemini 2.5 fallback on same API key
- Quality plateau: 3-cycle cap then unresolvable flag then auto-continue
- PII risk: zero real user data — all content is generated from briefs
- Reproducibility: deterministic seeds on all generation calls

### Phase 4: Competitive Intelligence

- Princeton Review: score stats, urgency, test date hooks — documented
- Khan Academy: free access, approachability, zero pressure — documented
- Kaplan: authority signals, score guarantees, structured credibility — documented
- Chegg: value positioning, free trial funnel, low-friction CTA — documented
- All patterns saved in `data/competitive_context.json` and injected into Drafter prompt

### Phase 5: Edge Cases Pre-Resolved

- **Image prompting:** Drafter outputs a 5th JSON field `image_prompt` — specific UGC-style visual instructions fed directly to Imagen, not a generic description
- **Context window in loop:** `controller.py` feeds back only the latest failed ad copy + weakest dimension rationale — no full history, keeps regeneration under 1,000 tokens per cycle
- **Calibration anchors:** Gold ad (8–10) and poor ad (1–4) examples hardcoded directly in `rubrics.py` — permanent reference point so judge scoring stays consistent across all 50+ ads

---

*End of Pre-Search Intelligence Report | Varsity Ad Engine | Nerdy / Gauntlet 2026*
