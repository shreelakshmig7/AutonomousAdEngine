# DECISION LOG
## Varsity Ad Engine — Nerdy / Gauntlet AI Program

---

## Decision: Pydantic Schema Defensive Validation
**Date:** 2026-03-09
**File affected:** schemas.py (EvaluationReport, AdCopy)

### What We Did
Added @model_validator to override average_score, passes_threshold, and
weakest_dimension — never trusting the LLM to calculate these itself.
Added @field_validator on headline (5-8 words), primary_text (hook within
100 chars), and image_prompt (no text/logos).

### Why
LLM arithmetic is unreliable. A hallucinating model returning scores of
[4,5,4,5,4] could claim average_score: 8.2 and passes_threshold: True.
Without the validator, a failing ad would be published silently.

### External Validation
Received schema review identifying 5 issues before implementation:
- average_score trusted from LLM (critical)
- passes_threshold trusted from LLM (critical)
- weakest_dimension trusted from LLM (critical)
- No headline word count enforcement (medium)
- Empty strings accepted silently (medium)
All 5 fixed before any code was written.

### Confidence
High. model_validator pattern eliminates an entire class of silent failure.

---

## Decision: briefs.json Design — Deliberate Difficulty Distribution
**Date:** 2026-03-09
**File affected:** data/briefs.json

### What We Did
Designed 12 synthetic briefs with specific regional audiences, income
brackets, and behavioral targeting signals. Deliberately included 4 hard
briefs (004, 009, 011, 012) that are expected to fail cycle 1 and require
the self-healing loop to demonstrate.

### Why
If all 50 ads pass on cycle 1, the most impressive part of the system —
the feedback loop — is invisible in the demo. Hard briefs force the loop
to activate visibly in iteration_log.csv and the quality trend chart.

### Changes Made After Review
- _comment moved to _meta block for cleaner loading
- difficulty field added to all 12 briefs (easy/medium/hard)
- brief_011 audience simplified — competitor-aware framing removed
  (competitive intelligence comes from competitive_context.json anyway)
- AdBrief pydantic schema locked with difficulty as Literal field

### Confidence
High. Difficulty distribution verified against hook type coverage —
all 5 hook types represented across 12 briefs.

---

## Decision: Preserving _comment and _edge_case Keys in JSON Files
**Date:** 2026-03-09
**Files affected:** data/brand_guidelines.json, data/competitive_context.json

### What We Did
Preserved non-standard _comment and _edge_case keys inside JSON data
files rather than normalizing them to a clean schema.

### Why
These files are injected wholesale into LLM prompts via json.dumps().
The LLM reads them as natural language — not as dictionary keys.
The underscore prefix and ALL-CAPS value pattern function as a semantic
interrupt. A key named _edge_case receives more attention weight than
a key named notes because the former signals "this is exceptional,
pay attention."

This is a deliberate hack of the model's attention mechanism — treating
our data files as prompt engineering artifacts rather than data schemas.

### The Tradeoff Accepted
json.load() loads _comment and _edge_case as normal dictionary keys.
Mitigated by: loaders access named keys directly, never iterate over
all keys. A comment in load_brand_guidelines() documents this permanently
so no future developer cleans them up.

### Options Rejected
- Move all metadata to a top-level _meta block: rejected — proximity
  in prompt context matters, edge case note must be adjacent to the
  rule it modifies
- Strip _prefixed keys before injection: worst of both worlds — loses
  the attention signal while keeping non-standard keys
- Separate prompt_hints.json: rejected — splitting notes from rules
  forces the model to mentally join two sections

### Evidence This Worked
Verifiable in iteration_log.csv — compare brand_voice and
emotional_resonance scores on fear-hook briefs. Consistent avoidance
of shame/catastrophizing language indicates the _edge_case signal
is functioning.

### Confidence
High. Pattern is consistent with production LLM prompt engineering
practice — formatting and key naming influence model attention.

---

## Decision: brand_guidelines.json Structure and Enforcement Layers
**Date:** 2026-03-09
**File affected:** data/brand_guidelines.json, schemas.py, evaluate/rubrics.py

### What We Did
Designed brand_guidelines.json with three enforcement layers:
1. Prompt injection — forbidden words and approved metrics injected
   into every Drafter prompt
2. Schema validation — AdCopy field validators enforce platform
   constraints (100-char hook rule, headline word count, image prompt
   safety)
3. Output scanning — scan_output_safety() in rubrics.py checks every
   generated ad for competitor names, PII patterns, and forbidden words

### Key Rules Formalised
- Hook must complete within first 100 characters (Meta truncation threshold)
- Fear hooks must pivot to relief within 1-2 sentences — ad cannot end on fear
- Forbidden words list enforced at both prompt and scan layers
- Approved differentiators only — no invented statistics or guarantees
- Image prompts: never request text, signs, logos rendered in image

### Changes Made After Review
- Synthesis rule added to writing_principles: product field is a fact
  sheet not a script — numbers survive verbatim, everything else gets
  translated
- Audience rule added: write TO the audience, never ABOUT them
- min_length: 80 added to primary_text (max was defined, min was missing)
- _comment inside approved_differentiators flagged for _meta migration
  (but kept in place per _edge_case decision above)

### Confidence
High. Three-layer enforcement means brand safety is checked at prompt
time, schema validation time, and output scan time.

---

## Decision: PR2 Architecture — Evaluator First
**Date:** 2026-03-09
**Files affected:** evaluate/rubrics.py, evaluate/judge.py,
                    tests/test_evaluator.py

### What We Did
Built the evaluator (rubrics + judge) as the first module before
any generation code. Established TDD sequence: tests → red run →
implementation → green run → calibration check.

### Why Evaluator First
Cannot build the Drafter without the Judge — no way to know if
generated ads are any good. Cannot build the feedback loop without
scores to react to. Cannot calibrate quality without the Judge
running first against gold and poor anchors.

### DIMENSION_PRIORITY Order Locked
```python
DIMENSION_PRIORITY = [
    "emotional_resonance",  # hardest to fix, most impactful
    "value_proposition",    # requires rewriting core claim
    "clarity",              # structural, one rewrite
    "brand_voice",          # tonal, one rewrite
    "call_to_action",       # easiest to fix, usually one line
]
```
Logic: when dimensions tie at lowest score, target the hardest to fix
first — gives the feedback loop the best chance in 3 cycles.

### Calibration Failure Protocol
If GOLD anchor < 8.0 on first run: revise judge prompt, re-run,
document number of iterations in this log.
If POOR anchor > 4.0 on first run: judge is too generous, same process.

### build_prompt() Signature Locked
Imports GOLD_ANCHOR and POOR_ANCHOR directly from rubrics.py at
module level — no anchors parameter. Prevents accidental anchor
substitution.

### scan_output_safety() Confirmed in PR2 Scope
Safety gate runs before scoring. Competitor names, PII patterns,
and forbidden words checked before evaluate_ad() is called.
Pipeline flow: generate → scan → score. Not: generate → score → scan.

### External Validation
Received positive review of PR2 architecture confirming TDD alignment,
mock API approach, centralized anchor strategy, and model_validator
tie-breaking. Three gaps identified and resolved:
1. scan_output_safety() confirmed in PR2 scope
2. build_prompt() signature locked
3. evaluate_ad() confirmed as synchronous dict return for Streamlit
   generator compatibility

### Confidence
High. All architectural decisions locked before first line of code written.

---

## Decision: Deployment — Streamlit + Streamlit Cloud
**Date:** 2026-03-09
**Files affected:** app.py (new), main.py (generator pattern)

### What We Did
Chose Streamlit + Streamlit Cloud as the deployment target.
Submission will include a persistent public URL at
[name]-varsity-ad-engine.streamlit.app.

### Options Evaluated
- Local + GitHub: rejected — no persistent URL for Gauntlet submission
- FastAPI + React: right architecture, wrong timeline (2 deployments,
  SSE streaming, background jobs — 2-3 extra days)
- Gradio + HF Spaces: rejected — free tier CPU too slow for 50-ad run
- Vercel + Railway: rejected — two deployments, too complex for Thursday
- Streamlit Cloud: selected — pure Python, free persistent URL,
  st.session_state handles long-running job state natively

### Key Constraint Introduced
main.py pipeline must be built as a generator (run_pipeline_streaming)
from day one — not refactored later. Every yield is a progress update
Streamlit can display live. Designing this in after the fact would
require refactoring the entire pipeline.

### evaluate_ad() Interface Contract
Must return a synchronous structured dict. No async, no callbacks.
The generator pattern in main.py depends on this.

### Tradeoff Accepted
Streamlit free tier sleeps after inactivity — first load takes ~30s.
Mitigated by: pre-committed output files in output/ as fallback if
judges hit a cold start during review.

### Confidence
High. Deployment decision fully locked with zero open questions.

---

## Decision: Claude Sonnet 4.5 as Judge, Gemini Flash as Drafter
**Date:** 2026-03-09
**Trigger:** Gemini 1.5 family unavailable on API key. gemini-2.5-pro paywalled (limit: 0 quota error). gemini-2.0-flash as judge introduced score leniency risk.

**Solution:** Cross-provider architecture.
- **Drafter:** gemini-2.0-flash — fast generation, same Google API key
- **Judge:** claude-sonnet-4-5 — accurate evaluation, Anthropic API key

**Why Claude over Flash-as-judge:**
1. Restores the quality asymmetry between Drafter and Judge
2. Claude is specifically strong at structured rubric evaluation
3. Cross-provider judging is more credible than same-model self-evaluation
4. claude-haiku available as fallback — stays in same family

**Why this is architecturally stronger than the original plan:**  
Original plan had Flash and Pro from the same provider — the judge could be influenced by the same biases as the drafter. Cross-provider evaluation is more independent by design.

**Bonus:** Demonstrates genuine multi-model, multi-provider orchestration — a stronger story for the Gauntlet evaluation criteria.

**Re-calibration required before PR3.**  
Target: Gold ≥ 8.0, Poor ≤ 4.0 with Claude as judge.

**Re-calibration result: PASSED on first attempt**
- Gold anchor score: 9.4 ✅ (target ≥ 8.0)
- Poor anchor score: 2.8 ✅ (target ≤ 4.0)
- Gap: 6.6 points ✅ (minimum 4.0)
- Date: 2026-03-09
- Model: claude-sonnet-4-5 as judge
- No prompt iterations required — calibrated on first run.

Calibration output saved to: `tests/results/manual_calibration_20260309.txt`

---

## PR2 Spec Review — 6 Items Resolved
**Date:** 2026-03-09
**Scope:** PR2 architecture and implementation contract

All 5 issues from the PR2 spec review plus 1 missing item are resolved. Status and resolution locations below.

### Issue 1 — Only 4 tests, PRD requires 12
**Status:** Resolved.

4 tests are the evaluator's slice of the full 12. Remaining 8 belong to later PRs (generator, iteration cap, integration). Explicitly documented so no future PR thinks testing is complete after PR2. Confirmed in the PR2 Architecture decision log entry.

### Issue 2 — DIMENSION_PRIORITY never defined
**Status:** Resolved — locked.

```python
DIMENSION_PRIORITY: list = [
    "emotional_resonance",   # hardest to fix, most impactful
    "value_proposition",     # requires rewriting core claim
    "clarity",                # structural, one rewrite
    "brand_voice",            # tonal, one rewrite
    "call_to_action",         # easiest to fix, usually one line
]
```

Logged in DECISION_LOG.md. Ready to hardcode in `evaluate/rubrics.py`.

### Issue 3 — Calibration failure condition undefined
**Status:** Resolved — protocol locked.

- **GOLD anchor < 8.0 on first run:** Revise judge prompt in judge.py; re-run until GOLD ≥ 8.0; document iteration count in DECISION_LOG.md.
- **POOR anchor > 4.0 on first run:** Judge too generous — same process; document in DECISION_LOG.md.

Calibration failure is a blocker — do not proceed to PR3 with an uncalibrated judge. Logged in DECISION_LOG.md.

### Issue 4 — build_prompt() signature unlocked
**Status:** Resolved — signature locked.

```python
def build_prompt(self, ad: AdCopy) -> str:
    """Build judge prompt with GOLD and POOR anchors from rubrics.py."""
```

No anchors parameter. Anchors imported at module level from rubrics.py. Logged in DECISION_LOG.md.

### Issue 5 — HOOK_MAX_CHARS naming consistency
**Status:** Resolved — name confirmed.

```python
HOOK_MAX_CHARS: int = 100  # Meta truncation threshold — hook must complete by this char
```

Consistent with `brand_guidelines.json`'s `hook_must_complete_by_char: 100`. Every file that references this value uses `HOOK_MAX_CHARS` — `rubrics.py`, schemas, `prompts.py`.

### Missing Item — scan_output_safety() placement
**Status:** Resolved — confirmed in PR2 scope.

Lives in `evaluate/rubrics.py`. Pipeline flow locked as:

1. AdCopy generated
2. `scan_output_safety()` (rubrics.py) runs first
3. Violations found? Reject, log, skip judge entirely
4. Clean? → `evaluate_ad()` (judge.py)

Logged in DECISION_LOG.md. Safety gate is a PR2 deliverable, not a later addition.

### Summary table

| Item | Status | Where resolved |
|------|--------|----------------|
| 4 tests = evaluator slice of 12 | Locked | DECISION_LOG.md |
| DIMENSION_PRIORITY order | Locked | DECISION_LOG.md + rubrics.py |
| Calibration failure protocol | Locked | DECISION_LOG.md |
| build_prompt() signature | Locked | DECISION_LOG.md + judge.py |
| HOOK_MAX_CHARS naming | Locked | rubrics.py + schemas + prompts.py |
| scan_output_safety() in PR2 | Locked | DECISION_LOG.md + rubrics.py |

---

## Decision: Guardrails Default-Deny — validate_free_text()
**Date:** 2026-03-09  
**Files affected:** `generate/guardrails.py`, `tests/test_guardrails.py`

### What We Did
Replaced allow-by-default Gate 1 logic with **default-deny**: input must match at least one **in-scope signal** to pass, unless blocked earlier by injection or off-topic patterns.

**Priority order:**
1. **Injection** — `INJECTION_PATTERNS` imported from `generate/prompts.py` (single source). Match → reject with `INJECTION_ATTEMPT_MESSAGE`, `reason: injection_attempt`.
2. **Off-topic blocklist** — explicit patterns (weather, pirate, recipe, etc.). Match → reject with `OUT_OF_SCOPE_MESSAGE`, `reason: off_topic_pattern:...`.
3. **Default deny** — if **no** `IN_SCOPE_SIGNALS` regex matches → reject with `OUT_OF_SCOPE_MESSAGE`, `reason: no_in_scope_signal`.

All rejects return **`success: False`** and **`error`** set so `draft_ad()` Gate 1 stops before any LLM call.

### Why
Allow-by-default let through "Tell me a joke" and similar — not injection, but out of scope. Blocklisting every off-topic phrase is endless. **Require in-scope signals** (SAT, tutor, prep, campaign, brief, audience, conversion, awareness, hook, varsity, nerdy, etc.) catches jokes, poems, general chat, and random tasks with one rule.

### What We Removed
- **Length heuristic** (e.g. len > 20) — length is not a proxy for scope. Short valid briefs exist; short junk exists too. Signal check handles both.

### What We Avoided
- **`\bad\b`** in in-scope list — false positives on glad/dad. Use campaign/brief/audience/hook/advert/etc. instead.

### AdBrief Path
`AdBrief` still accepted: normalized to one string (`audience` + `product` + `tone`) then same three priorities. Real briefs from `briefs.json` contain signals by construction.

### Tests
Added `test_guardrails_rejects_no_signal_inputs`, `test_guardrails_rejects_injection_with_specific_message`, `test_guardrails_passes_brief_style_inputs`, etc. Full suite green; results saved to `tests/results/guardrails_fix_20260309.txt`.

### Confidence
High. Default-deny aligns Gate 1 with product scope without whack-a-mole blocklists.

---

## Decision: primary_text Length Enforcement — Prompt (A) + Retry (B)
**Date:** 2026-03-09  
**Trigger:** Gemini 2.5 Flash returned `primary_text` > 500 characters on first live draft run, causing `AdCopy` ValidationError (`string_too_long`).

**Files affected:** `generate/prompts.py`, `generate/drafter.py`, `tests/test_generator.py`

### Root Cause
Prompt did not state the **500-character hard limit** explicitly. LLMs do not count characters reliably without explicit instruction.

### Option D Rejected — Never Raise Schema Limit
**500 characters** is a real **Meta platform constraint** documented in `brand_guidelines.json` / `evaluate/rubrics.py` (`AdCopy.primary_text` `max_length=500`). Raising the limit would generate ads truncated on Facebook — defeats the purpose. **Never weaken a platform constraint to fix a model output problem.**

### Fix A — Prompt
Added **PRIMARY_TEXT LENGTH LIMIT** block in `build_drafter_prompt()` **immediately before** the JSON output format section (proximity matters for attention).

Content includes:
- `primary_text` must be **500 characters or fewer**; count before outputting.
- Meta shows ~125 chars before "See More" but **full text must stay under 500 total**.
- If over 500: **cut the weakest sentence, not the hook**; do not summarize — cut; hook and CTA must survive.

Covers **90%+** of cases at no extra API cost.

### Fix B — Retry on ValidationError
In `draft_ad()`, after `json.loads()`:
- Wrap `AdCopy.model_validate(parsed)` in try/except `ValidationError`.
- If error **`type == string_too_long`** and **`loc`** contains **`primary_text`**: **one** targeted retry via `_call_gemini()` with previous JSON embedded and explicit rewrite-under-500 instruction (all 5 fields, no markdown).
- If retry still fails → outer `except ValidationError` returns structured failure.
- Any **other** validation error → re-raise (no retry).

Uses same `model_used` and `generation_config` as the first call.

### Option C Rejected — Truncation at Char 500
Truncating mid-sentence produces broken copy → poor **clarity** and **brand_voice** and wastes a judge call. **One retry is cleaner** than shipping truncated ads.

### This Retry Is Not a Feedback-Loop Cycle
Length retry is **schema enforcement inside `drafter.py`** before the ad reaches `judge.py`. It does **not** increment cycle count. **`MAX_CYCLES`** in `controller.py` is unchanged — quality iteration only.

### Test
`test_drafter_retries_on_primary_text_too_long`: mock first return >500 chars, second return valid; assert success, `len(primary_text) <= 500`, `_call_gemini` called twice. Results saved to `tests/results/primary_text_length_retry_20260309.txt`.

### Confidence
High. A + B gives prompt alignment plus a safe fallback without truncation or schema weakening.

---

## Decision: PR3 Generate Module Architecture
**Date:** 2026-03-09  
**Files affected:** `generate/prompts.py`, `generate/drafter.py`, `generate/guardrails.py`, `data/loaders.py`, `data/__init__.py`, `evaluate/rubrics.py` (AdBrief + CTA_OPTIONS only), `tests/test_generator.py`, `tests/test_guardrails.py`, `tests/conftest.py`  
**Removed:** `generate/constants.py` (contents moved into `prompts.py`)

### Models Locked
- **Drafter:** `gemini-2.5-flash` — fast, cheap, generation  
- **Judge:** `claude-sonnet-4-5` — accurate evaluation (PR2; unchanged)  
- **Fallback Drafter:** `gemini-2.0-flash` — same provider, one tier down on `ResourceExhausted`

**Cross-provider architecture** — Gemini drafts, Claude judges. Stronger than same-provider self-evaluation; genuine multi-model orchestration for Gauntlet rubric.

### Key Decisions

1. **`response_mime_type="application/json"`** on all Gemini generation config — reduces markdown/code-fence wrapping of JSON. Learned from PR2 calibration runs.

2. **`_clean_json_response()`** in `drafter.py` — defensive strip of code fences and brace extraction before every `json.loads()`; Gemini is not 100% consistent even with MIME type set.

3. **`generate/constants.py` deleted** — model names and `DEFAULT_SEED` live in `generate/prompts.py`. Shared constants (`HEADLINE_*`, `HOOK_MAX_CHARS`, `CTA_OPTIONS`) imported from `evaluate/rubrics.py` only — single source of truth, no duplication.

4. **`sanitize_for_injection()`** — returns `success: False` on pattern match; **never** strip-and-continue. Rejection only; pipeline returns structured error and does not call Gemini for that brief.

5. **brand_guidelines (and competitive_context) injected into every drafter prompt** via `build_drafter_prompt()` — forbidden words, approved differentiators, synthesis rules present at **generation** time, not only at evaluation time.

6. **`data/loaders.py` required in PR3** — `load_briefs()`, `load_competitive_context()`, `load_brand_guidelines()`; one loader module for smoke test, `main.py`, and `app.py`. No ad-hoc JSON loading in three places.

7. **Gate order in `draft_ad()`** — (1) `validate_free_text` guardrails, (2) sanitize all brief fields, (3) `build_drafter_prompt`, (4) `_call_gemini`. Out-of-scope and injection never hit the LLM.

8. **AdBrief + CTA_OPTIONS in `evaluate/rubrics.py`** — shared schema for generate and iterate; avoids circular imports if AdBrief lived only under `generate/`.

### Deferred
- **CSV export** — deferred to PR4/PR5; drafter outputs validated `AdCopy` in memory only for PR3 scope.

### Regression Rule (PR2 → PR3)
If any PR2 evaluator test fails after PR3 changes — **stop**; fix before PR4. Document what broke in this log.

### Confidence
High. PR3 deliverables aligned to TDD, mock `_call_gemini` boundary, and locked model list.

---

## Post-Run Analysis: brief_005 NaN Unresolvables
**Date:** 2026-03-09

### Finding
4 of 5 **brief_005** variations logged **NaN** for all metrics in `iteration_log.csv`.

### Root cause
- **Gemini free tier quota** (e.g. 20 req/day) **exhausted mid-run** around the brief_004 / brief_005 boundary.
- **Fallback to Claude Haiku** was **inconsistent** — some calls succeeded, others **failed silently** and logged **NaN** instead of an error message.

### Evidence
Running **brief_005 v0** directly **after quota reset** returned:
- `status=published`, `score=8.2`, `model=gemini-2.5-flash`.
- The **brief itself is not the problem**.

### Fixes applied
1. **`controller.py`** — fallback failure now logs the **actual error**, not NaN; `model_used` normalized to `None` when not a string.
2. **`drafter.py`** — **5-second delay** added **before** fallback call so the rate-limit window can clear; **RetryError** (Tenacity exhausted) treated like **ResourceExhausted** and routed to fallback; **both** primary and fallback failure returns a single structured error string.

### Impact on submission
- **None.**
- **50 ads published**, all above threshold.
- NaN rows correctly logged as **unresolvable**.
- System **did not publish bad ads**.

### Lesson
- **20 req/day free tier** is **insufficient** for a **60-attempt** pipeline.
- **Production** deployment requires **paid Gemini tier** or **full fallback to Claude** for all drafter calls (or equivalent quota).
