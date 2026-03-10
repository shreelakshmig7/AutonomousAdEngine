# Task List — Varsity Ad Engine
### Based on: `docs/02_Product_Requirements_Document.md` + `docs/Coding_Standards.md`

---

## Relevant Files

- `requirements.txt` - Pinned exact dependency versions (supply chain safety)
- `.env` - API keys — never committed
- `.gitignore` - Ensures .env, output/, __pycache__ are excluded
- `data/briefs.json` - 10+ ad briefs covering all 5 hook types
- `data/competitive_context.json` - Competitor patterns from Meta Ad Library
- `data/brand_guidelines.json` - Varsity Tutors voice, differentiators, fear hook boundaries (Edge Case 5), banned patterns
- `evaluate/__init__.py` - Package init
- `evaluate/rubrics.py` - Constants + calibration anchors (GOLD/POOR) + Pydantic schemas
- `evaluate/judge.py` - Gemini Pro 5-dimension scorer
- `generate/__init__.py` - Package init
- `generate/prompts.py` - System prompt templates + ad copy constants
- `generate/drafter.py` - Gemini Flash drafter + tenacity fallback + security sanitization
- `iterate/__init__.py` - Package init
- `iterate/controller.py` - 3-cycle feedback loop + unresolvable logic
- `images/__init__.py` - Package init
- `images/image_generator.py` - Imagen / Nano Banana v2 image generation
- `output/ads_library.json` - 50+ passing ads with scores, rationales, image URLs
- `output/iteration_log.csv` - Cycle-by-cycle score tracking
- `output/quality_trends.png` - Matplotlib quality improvement chart
- `main.py` - Pipeline as generator — run_pipeline_streaming() yields progress for Streamlit
- `app.py` - Streamlit UI — calls run_pipeline_streaming(), displays live; deploy to Streamlit Cloud
- `tests/conftest.py` - Mocks API key and genai for evaluator tests (offline)
- `tests/test_evaluator.py` - 4 evaluator tests (gold, poor, threshold, weakest)
- `tests/results/run_pr2_green_20260309.txt` - PR2 green run proof
- `tests/test_iteration_cap.py` - 2 iteration cap tests (cap at 3, unresolvable)
- `tests/test_generator.py` - 5 generator tests (schema, CSV, seed, fallback, image URL)
- `tests/test_integration.py` - 1 end-to-end pipeline test
- `tests/results/` - TDD proof — saved test run outputs
- `docs/DECISION_LOG.md` - Human-written decision log (WHY, failures, limits)
- `README.md` - One-command cold-start setup instructions

### Notes

- TDD is mandatory: write test → confirm FAIL → write implementation → confirm PASS → save result
- All tests mock API calls via `pytest-mock` — runs fully offline
- Run tests: `pytest tests/ -v --tb=short 2>&1 | tee tests/results/run_YYYYMMDD.txt`
- Never edit files inside `/docs` — reference only

### Build Order (File-Level — Do Not Deviate)

```
1.  evaluate/rubrics.py         ← no dependencies; everything imports from here
2.  tests/test_evaluator.py     ← TDD red phase
3.  evaluate/judge.py           ← green phase
4.  generate/prompts.py         ← depends on knowing what judge rewards
5.  tests/test_generator.py     ← TDD red phase
6.  generate/drafter.py         ← green phase
7.  tests/test_iteration_cap.py ← TDD red phase
8.  iterate/controller.py       ← green phase
9.  tests/test_integration.py   ← TDD red phase
10. main.py                     ← build as GENERATOR (run_pipeline_streaming); yields progress
11. images/image_generator.py   ← v2
12. app.py                      ← Streamlit UI; calls run_pipeline_streaming(), displays live
13. Deploy to Streamlit Cloud   ← [yourname]-varsity-ad-engine.streamlit.app
```

**main.py:** Must yield progress (e.g. `{"status": "drafting", "brief_id": ...}`) so Streamlit can stream live. Do not build as a function that returns only at the end.

### Synthetic Data Strategy

Building with synthetic data now. Real data swap requires **zero code changes** — only these files update when Slack reference ads arrive:
- `data/briefs.json` — swap synthetic briefs for real campaign briefs
- `data/competitive_context.json` — enrich with real Meta Ad Library data
- `evaluate/rubrics.py` — update `GOLD_ANCHOR` with real top-performing ad

---

## Tasks

- [x] 1.0 PR1 — Project Foundation & Infrastructure
  - [x] 1.1 Update `requirements.txt` with exact pinned versions per Coding Standards §13.4
  - [x] 1.2 Create `.gitignore` covering `.env`, `output/`, `__pycache__/`, `*.pyc`, `.DS_Store`
  - [x] 1.3 Create `.env.example` with `GOOGLE_API_KEY=your_key_here` placeholder
  - [x] 1.4 Create `data/briefs.json` with 10+ briefs covering all 5 hook types (question, stat, story, fear, empathy), both goals (awareness, conversion)
  - [x] 1.5 Create `data/competitive_context.json` with Princeton Review, Khan Academy, Kaplan, Chegg patterns from pre-search intelligence
  - [x] 1.6 Create `data/brand_guidelines.json` with Varsity Tutors voice rules, differentiators, banned patterns
  - [x] 1.7 Create all `__init__.py` files for `generate/`, `evaluate/`, `iterate/`, `images/` packages
  - [x] 1.8 Create `output/` and `tests/results/` directories with `.gitkeep`

- [ ] 2.0 PR2 — Evaluate Module (Judge + Rubrics) — Sunday Goal
  - [x] 2.1 Write `tests/test_evaluator.py` first (TDD red phase) — all 4 tests with mocked API
  - [x] 2.2 Confirm all 4 tests FAIL and save results to `tests/results/`
  - [x] 2.3 Create `evaluate/rubrics.py`:
    - All quality constants: `QUALITY_THRESHOLD`, `MAX_CYCLES`, `DIMENSIONS`, `EXCELLENT_THRESHOLD`
    - `DIMENSION_PRIORITY` list for tie-breaking (Edge Case 4)
    - `HOOK_MAX_CHARS = 100` constant (Edge Case 2)
    - `GOLD_ANCHOR` + `POOR_ANCHOR` dicts (hardcoded, never generated)
    - `AdCopy` Pydantic schema with validators:
      - `headline_word_count` (5–8 words)
      - `hook_in_first_100_chars` — first sentence must end within 100 chars (Edge Case 2)
      - `no_text_in_image_prompt` — reject prompts requesting rendered text/signs (Edge Case 6)
    - `DimensionScore` + `EvaluationReport` schemas with `@model_validator` that computes `average_score`, `passes_threshold`, and `weakest_dimension` using `DIMENSION_PRIORITY` tie-breaking (Edge Case 4)
    - `scan_output_safety()` in PR2 scope — runs before scoring (competitor names, forbidden words, PII)
  - [x] 2.4 Create `evaluate/judge.py` — `AdJudge` class with `evaluate_ad()` calling Gemini 1.5 Pro, `build_prompt()` injecting calibration anchors, structured dict returns, full error handling
  - [x] 2.5 Run tests — confirm all 4 PASS (green), save results
  - [ ] 2.6 Manual calibration check: gold anchor scores >= 8.0, poor anchor scores <= 4.0

- [ ] 3.0 PR3 — Generate Module (Drafter + Prompts)
  - [ ] 3.1 Write `tests/test_generator.py` first (TDD red phase) — all 5 generator tests with mocked API
  - [ ] 3.2 Confirm all 5 tests FAIL and save results
  - [ ] 3.3 Create `generate/prompts.py`:
    - All ad copy constants: `HEADLINE_MIN/MAX_WORDS`, `CTA_OPTIONS`, `BRAND_DIFFERENTIATORS`, `HOOK_TYPES`
    - Finalized Drafter system prompt with:
      - Truncation rule: hook must appear in first 100 chars (Edge Case 2)
      - Negative prompt section: approved metrics only, no invented stats/offers (Edge Case 3)
      - Fear hook boundary: no shaming, no catastrophizing, always pivot to relief (Edge Case 5)
      - Image prompt rules: no text/signs/logos in image, visual scenes only (Edge Case 6)
    - `build_drafter_prompt()` with `{competitive_context}` and `{brief}` injection
    - `sanitize_for_injection()` security function (Coding Standards §13.1)
  - [ ] 3.4 Create `generate/drafter.py` — `AdDrafter` class with `draft_ad()` calling Gemini 1.5 Flash, `DEFAULT_SEED` on all calls, tenacity retry with `FALLBACK_DRAFTER_MODEL` on `ResourceExhausted`, full error handling
  - [ ] 3.5 Run tests — confirm all 5 PASS (green), save results

- [ ] 4.0 PR4 — Iterate Module + Main Pipeline (50+ Ads)
  - [ ] 4.1 Write `tests/test_iteration_cap.py` first (TDD red phase) — both iteration tests with mocked API
  - [ ] 4.2 Confirm both tests FAIL and save results
  - [ ] 4.3 Create `iterate/controller.py`:
    - `AdController` class with `run_brief()` orchestrating the 3-cycle loop
    - `build_regeneration_prompt()` — anchors passing scores, targets only `weakest_dimension` (Edge Case 1: Whac-A-Mole fix)
    - Format: "You scored X/10 on [passing dimensions] — preserve these. Rewrite ONLY [weakest_dimension]."
    - Context window: < 1,000 tokens, no full history, weakest rationale stripped to 200 chars
    - `unresolvable` status logic + structured logging
  - [ ] 4.4 Run iteration tests — confirm both PASS (green), save results
  - [ ] 4.5 Create `main.py` as a **generator** `run_pipeline_streaming(briefs, competitive_context, brand_guidelines)` that yields progress (e.g. `{"status": "drafting", "brief_id": ...}`); CLI iterates over it with `rich` live progress; write `ads_library.json` + `iteration_log.csv`; validate 50+ ads produced
  - [ ] 4.6 Write `tests/test_integration.py` (TDD red), implement, confirm PASS, save results
  - [ ] 4.7 Run full pipeline end-to-end: confirm `ads_library.json` has 50+ passing entries

- [ ] 5.0 PR5 — v2 Image Generation + Quality Visualization
  - [ ] 5.1 Create `images/image_generator.py` — `AdImageGenerator` class with `generate_image()` calling Imagen / Nano Banana, saves to `output/images/`, returns `image_url`, only runs on ads passing threshold
  - [ ] 5.2 Wire image generation into `main.py` — each passing ad triggers `generate_image()` with its `image_prompt`, `image_url` saved to `ads_library.json`
  - [ ] 5.3 Add `output/quality_trends.png` generation to `main.py` — matplotlib/seaborn chart of average score per cycle across all briefs, must show measurable upward slope
  - [ ] 5.4 Verify `output/iteration_log.csv` captures all fields: `brief_id`, `difficulty`, `cycle`, all 5 dimension scores, `average_score`, `weakest_dimension`, `status`, `tokens_used`, `cost_usd`
  - [ ] 5.5 Run regression: `pytest tests/ -v` — confirm all previously passing tests still pass

- [ ] 6.0 PR6 — Documentation, README & Submission Polish
  - [ ] 6.1 Write `README.md` — one-command cold-start (`python main.py`), Streamlit (`streamlit run app.py`), prerequisites, `.env` setup, output file descriptions, test run instructions
  - [ ] 6.2 Write `docs/DECISION_LOG.md` — document all key decisions (incl. Streamlit + generator pattern; WHY Flash vs Pro, 5 dimensions, 7.0 threshold, 3 cycles, competitive intelligence, failures, perf-per-token, limitations)
  - [ ] 6.3 Run full test suite final time: `pytest tests/ -v --tb=short 2>&1 | tee tests/results/final_run.txt` — all 12 tests must pass
  - [ ] 6.4 Cold-start verification — delete all output files, run `python main.py` from scratch, confirm 50+ ads generated
  - [ ] 6.5 Verify no automatic deductions: 50+ ads ✓, evaluation scores on all ads ✓, iteration attempted ✓, working demo ✓, decision log ✓

- [ ] 7.0 PR7 — Streamlit UI & Deployment
  - [ ] 7.1 Create `app.py` — Streamlit UI that calls `run_pipeline_streaming()`, displays each yielded progress update live; does not modify pipeline logic
  - [ ] 7.2 Add `streamlit` to `requirements.txt`
  - [ ] 7.3 Deploy to Streamlit Cloud — submission URL: `[yourname]-varsity-ad-engine.streamlit.app`
  - [ ] 7.4 Record demo video — screen recording of Streamlit run
  - [ ] 7.5 Submission package: GitHub repo URL + Streamlit app URL + demo video; commit output files to repo as fallback (app may sleep on free tier)
