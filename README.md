# Autonomous Ad Engine

A multi-agent AI system that generates publishable Facebook/Instagram ad creative from briefs — autonomously, in ~10 minutes, held to a hard 7.0/10 quality bar.

**Live dashboard:** https://autonomousadengine-tqujd9x5ndqhxzwfqscxjr.streamlit.app/

---

## What It Does

Most AI content pipelines output drafts and rely on humans to filter what's publishable. The Autonomous Ad Engine answers a different question: what if the system could self-evaluate and heal its own failures?

Three specialized agents work together:

- **Drafter** — Gemini 2.5 Flash writes ad copy (headline, primary text, description, CTA) and an image prompt for each ad.
- **Judge** — Claude Sonnet 4.5 scores every ad across five dimensions (Value Prop, Clarity, Emotion, Brand Voice, CTA) on a 1–10 scale with a per-dimension rationale.
- **Controller** — orchestrates a self-healing loop. On failure, it identifies the weakest dimension, builds a targeted regeneration prompt with dimension-specific fix strategies, and sends it back to the Drafter. Max 3 cycles, then logged as unresolvable.

Passing ads get a companion image from a Phase 2 image pass (Gemini 2.5 Flash Image). Every decision — every Judge score, every regeneration cycle, every cost line — is logged end-to-end.

Built initially for Shreelakshmi Tutors' SAT prep ad campaigns, the pipeline is brief-agnostic and works for any brand with a `brand_guidelines.json` + `briefs.json` pair.

---

## Results

| Metric | Value |
| --- | --- |
| Ads published per run | **62** out of 75 attempts (15 briefs × 5 variations) |
| Pass rate through self-healing | **83%** |
| Average quality across published ads | **8.3 / 10** |
| End-to-end runtime | **~10 minutes** |
| Quality threshold | 7.0 / 10 average across 5 dimensions |
| Iteration cap | 3 cycles per variation |

---

## Key Engineering Highlights

**1. Bookended prompt structure.** Critical constraints are anchored at the TOP and BOTTOM of the Drafter prompt to counter the Lost-in-the-Middle effect. Few-shot GOOD/BAD examples live in the middle, and dimension-specific `say-X-not-Y` fix strategies drive targeted regeneration rather than generic "try again" retries.

**2. Two-tier concurrency with finally-block throttling.** A `ThreadPoolExecutor` dispatches pipeline jobs layered over per-provider semaphores (5 Gemini, 2 Anthropic). Each Claude call holds its semaphore slot through a 2-second pacing delay inside the `finally` block — making threads wait before releasing the slot, not after. That one detail is the difference between clean runs and cascading 429 rate-limit failures under Anthropic Tier 1's 30K TPM cap.

**3. Phase 2 image pass.** Text and image budgets are decoupled. The quality loop runs first, paying only Gemini text + Claude judge tokens; images generate in a second pass only after an ad has already passed. Rejected drafts never burn image spend.

**4. Full traceability.** Every Judge evaluation, every regen cycle, every score lands in `output/runs/<run_id>/iteration_log.csv`. If an ad fails, you can see exactly which dimension was weakest, how the regeneration prompt was retargeted, and why the ad was eventually published or marked unresolvable.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for pipeline diagrams, component reference, and the full concurrency + rate-limiting model.

---

## Tech Stack

- **Python 3.10+**
- **LLMs:** Gemini 2.5 Flash (drafter + image generation), Claude Sonnet 4.5 (judge), Claude Haiku 4.5 (fallback drafter on Gemini rate limit)
- **SDKs:** `google-generativeai`, `anthropic`
- **Structured output:** Pydantic v2 for enforced JSON schemas on every LLM call
- **Resilience:** Tenacity for exponential backoff retries + custom semaphore-based rate limiter
- **Dashboard:** Streamlit 1.45.1 (deployed on Streamlit Cloud)
- **Visualization:** Matplotlib, Seaborn

---

## Getting Started

### Prerequisites

- Python 3.10+ (3.10–3.12 recommended; Streamlit Cloud uses this range)
- Google AI Studio API key ([get one](https://aistudio.google.com))
- Anthropic API key ([get one](https://console.anthropic.com))

### 1. Clone and install

```bash
git clone https://github.com/shreelakshmig7/AutonomousAdEngine.git
cd AutonomousAdEngine
python3.10 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment

```bash
cp .env.example .env
```

Edit `.env` and set:

- `GOOGLE_API_KEY` — for the Gemini drafter and image generator
- `ANTHROPIC_API_KEY` — for the Claude Sonnet judge and Haiku fallback

Optional overrides (see `.env.example` for the full list):

- `PIPELINE_MAX_WORKERS=5` — parallel brief/variation workers
- `GEMINI_MAX_CONCURRENT=5` — semaphore cap on concurrent Gemini calls
- `ANTHROPIC_MAX_CONCURRENT=2` — semaphore cap on concurrent Anthropic calls
- `ANTHROPIC_CALL_DELAY=2.0` — seconds of pacing delay held inside `finally` before releasing the Anthropic semaphore
- `VARIATIONS_PER_BRIEF=5`, `MAX_CYCLES=3`, `QUALITY_THRESHOLD=7.0`

> **Do not commit `.env`** — it is listed in `.gitignore`.

### 3. Run the pipeline (CLI)

```bash
python main.py
```

Loads `data/briefs.json`, `data/competitive_context.json`, and `data/brand_guidelines.json`, runs the full pipeline (draft → judge → regen up to 3 cycles per variation), generates companion images in a Phase 2 pass, and writes outputs to `output/runs/<timestamp>/`. Progress is printed live with a Rich table.

### 4. Run the Streamlit dashboard

```bash
streamlit run app.py
```

Five pages: **Dashboard** (metrics + charts), **Library** (browse all passing ads with filters), **Self-Healing** (per-evaluation trace log), **Run Pipeline** (trigger runs + live logs), **Settings**.

For Streamlit Cloud deployments, set `GOOGLE_API_KEY` and `ANTHROPIC_API_KEY` in the app's Secrets.

---

## Outputs

| Location | Description |
|----------|-------------|
| `output/runs/<run_id>/ads_library.json` | All published ads with copy, scores, rationales, image paths, tokens, cost |
| `output/runs/<run_id>/iteration_log.csv` | One row per evaluation event: brief, variation, cycle, dimension scores, status, tokens, cost |
| `output/runs/<run_id>/quality_trends.png` | Average score by cycle (improvement over iterations) |
| `output/runs/<run_id>/images/` | Companion images for passing ads (e.g. `brief_001_v0.png`) |
| `output/ads_library.json` | Copy of the latest run's `ads_library.json` |
| `output/quality_trends.png` | Copy of the latest run's quality trend chart |

---

## Tests

All tests mock external APIs and run offline:

```bash
pytest tests/ -v --tb=short
```

Save a run for records:

```bash
pytest tests/ -v --tb=short 2>&1 | tee tests/results/run_$(date +%Y%m%d).txt
```

---

## Project Layout

```
├── generate/              # Drafter (Gemini Flash), prompts, guardrails
│   ├── drafter.py
│   ├── prompts.py         # Bookended prompt structure with few-shot examples
│   └── guardrails.py
├── evaluate/              # Judge (Claude Sonnet), rubrics, calibration anchors
│   ├── judge.py
│   └── rubrics.py         # 5-dimension scoring schema + DIMENSION_FIX_STRATEGIES
├── iterate/               # Self-healing controller (3-cycle loop, weakest-dimension regen)
│   └── controller.py
├── images/                # Phase 2 image generation (Gemini 2.5 Flash Image)
│   └── image_generator.py
├── data/                  # briefs.json, competitive_context.json, brand_guidelines.json
├── output/                # Per-run outputs: ads_library, iteration_log, charts, images
├── docs/                  # Architecture, PRD, Decision Log, Coding Standards, Pre-Search Report
├── tests/                 # Integration + unit tests (all mock external APIs)
├── rate_limiter.py        # Per-provider semaphores + Anthropic call-delay throttle
├── constants.py           # Shared configuration constants
├── main.py                # CLI entrypoint; `run_pipeline_streaming()` generator
└── app.py                 # Streamlit dashboard entry
```

---

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Pipeline flow, component diagrams, concurrency + rate-limiting model, and bookended prompt structure
- [`docs/02_Product_Requirements_Document.md`](docs/02_Product_Requirements_Document.md) — Product requirements, configuration reference, and Drafter prompt specification
- [`docs/DECISION_LOG.md`](docs/DECISION_LOG.md) — Design decisions, tradeoffs, and failure modes (prompt restructure, rate-limit throttling, image pass decoupling, etc.)
- [`docs/Coding_Standards.md`](docs/Coding_Standards.md) — Style, testing patterns, and rate-limiting best practices
- [`docs/01_PreSearch_Intelligence_Report.md`](docs/01_PreSearch_Intelligence_Report.md) — Pre-work research and decision rationale

---

## License

Personal engineering project built to explore multi-model AI orchestration, autonomous quality loops, and production-grade rate-limit engineering. See `docs/` for full technical context.
