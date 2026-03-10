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
