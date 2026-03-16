# Varsity Ad Engine

Autonomous ad generation system for Varsity Tutors (Nerdy). Generates Facebook/Instagram ad copy from briefs, scores it on five dimensions (clarity, value proposition, call-to-action, brand voice, emotional resonance), and iterates up to 3 cycles until copy meets a 7.0/10 quality threshold. Passing ads get companion images and all runs are logged for quality trends and cost tracking.

---

## Prerequisites

- **Python 3.10+** (3.10–3.12 recommended; Streamlit Cloud uses this range)
- API keys (see [Environment](#environment))

---

## Quick start

### 1. Clone and install

```bash
git clone <repo-url>
cd AutonomousAdEngine
python3.10 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment

Copy the example env file and add your keys:

```bash
cp .env.example .env
```

Edit `.env` and set:

- **`GOOGLE_API_KEY`** — for the drafter (Gemini) and image generator ([Google AI Studio](https://aistudio.google.com))
- **`ANTHROPIC_API_KEY`** — for the judge (Claude) ([Anthropic Console](https://console.anthropic.com))

Optional: `IMAGE_GEN_MODEL`, `JUDGE_MODEL`, etc. (see `.env.example`).

**Do not commit `.env`** — it is listed in `.gitignore`.

### 3. Run the pipeline (CLI)

From the project root:

```bash
python main.py
```

This loads `data/briefs.json`, `data/competitive_context.json`, and `data/brand_guidelines.json`, runs the full pipeline (draft → judge → regen up to 3 cycles per variation), and writes outputs. Progress is printed in the terminal with a Rich table.

### 4. Run the Streamlit dashboard

```bash
streamlit run app.py
```

The app runs the pipeline (via `main.py`) and shows run selector, metrics, charts, and ad browser. For Streamlit Cloud, set `GOOGLE_API_KEY` and `ANTHROPIC_API_KEY` in the app’s Secrets.

---

## Outputs

| Location | Description |
|----------|-------------|
| **`output/runs/<run_id>/`** | Each run gets a timestamped folder (e.g. `20260315_120000`). |
| **`output/runs/<run_id>/ads_library.json`** | All published ads (copy, scores, rationales, image URLs, tokens, cost). |
| **`output/runs/<run_id>/iteration_log.csv`** | One row per evaluation event: brief, variation, cycle, dimension scores, status, tokens, cost. |
| **`output/runs/<run_id>/quality_trends.png`** | Matplotlib chart of average score by cycle (improvement over iterations). |
| **`output/runs/<run_id>/images/`** | Companion images for passing ads (e.g. `brief_001_v0.png`). |
| **`output/ads_library.json`** | Copy of the latest run’s `ads_library.json`. |
| **`output/quality_trends.png`** | Copy of the latest run’s quality trend chart. |

Target: **50+ published ads** per full run (15 briefs × 5 variations; some may end as `unresolvable` after 3 cycles).

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

## Project layout

```
├── generate/          # Drafter (Gemini Flash), prompts, guardrails
├── evaluate/          # Judge (Claude), 5-dimension rubrics, calibration anchors
├── iterate/            # 3-cycle controller, regen prompt, unresolvable handling
├── images/             # Companion image generation (Gemini 2.5 Flash Image)
├── data/               # briefs.json, competitive_context.json, brand_guidelines.json
├── output/             # ads_library.json, quality_trends.png, runs/<run_id>/
├── main.py             # CLI entrypoint; run_pipeline_streaming() generator
├── app.py              # Streamlit UI
└── tests/              # test_evaluator, test_generator, test_iteration_cap, test_integration, etc.
```

---

## Submission

- **[SUBMISSION.md](SUBMISSION.md)** — Checklist for repo URL, Streamlit app URL, demo video, and optional output run commit (PR7.5).

## Docs

- **[Architecture](ARCHITECTURE.md)** — Agent architecture, pipeline flow, and component diagrams.
- **`docs/02_Product_Requirements_Document.md`** — PRD (read-only reference).
- **[Decision Log](docs/DECISION_LOG.md)** — Design decisions, failures, and limitations (human-maintained).
- **[Pre-Search Report (implementation-aligned)](memory-bank/PreSearch_Intelligence_Report_Implementation.md)** — As-built alignment with `docs/01_PreSearch_Intelligence_Report.md` (models, SDKs, schemas, flow).

---

## License and attribution

Varsity Ad Engine — Nerdy / Gauntlet. See repository and `docs/` for full context.
