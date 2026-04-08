"""
controller.py
-------------
Shreelakshmi Ad Engine — Shree / Gauntlet — Iteration controller (PR4)
-------------------------------------------------------------------
run_brief() orchestrates draft → pre-judge repair cap (schema/safety) → judge →
quality regen. Logged cycle 1..N is the Nth judge evaluation only (not repair
loops). build_regeneration_prompt() uses a surgical Senior Ad Copy Editor persona.

Key constants / functions:
  DIMENSION_TO_GUIDELINE_KEY — map dimension to brand_guidelines slice
  run_brief()               — MAX_EVALUATION_CYCLES judge passes; pre-judge repairs capped
  build_regeneration_prompt() — surgical multi-dimension regen prompt
  _editor_regen()           — Gemini JSON editor call + AdCopy validation
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from evaluate.rubrics import (
    AdBrief,
    AdCopy,
    DIMENSION_DISPLAY_NAMES,
    DIMENSIONS,
    EvaluationReport,
    GOLD_ANCHOR,
    MAX_DRAFT_RETRIES_NO_MINIMAL,
    MAX_EVALUATION_CYCLES,
    MAX_PRE_JUDGE_REPAIR_ATTEMPTS,
    QUALITY_THRESHOLD,
    STRONG_DIMENSION_THRESHOLD,
    scan_output_safety,
)
from generate.drafter import AdDrafter
from generate.guardrails import validate_free_text
from generate.prompts import DEFAULT_SEED, sanitize_for_injection
from evaluate.judge import AdJudge

# -----------------------------------------------------------------------------
# Dimension → brand_guidelines slice (PR4 briefing; testable)
# -----------------------------------------------------------------------------
DIMENSION_TO_GUIDELINE_KEY: dict[str, list[str]] = {
    "brand_voice": ["voice", "forbidden_words_and_phrases"],
    "emotional_resonance": ["hook_guidelines", "fear_hooks"],
    "clarity": ["voice", "writing_principles"],
    "value_proposition": ["approved_differentiators", "metrics"],
    "call_to_action": ["cta_guidelines"],
}

REASONABLE_RATIONALE_MAX_CHARS: int = 200
# When multiple weak dimensions, cap rationale length so prompt stays bounded

# Dimension-specific rewriting strategies — concrete guidance for the Drafter
DIMENSION_FIX_STRATEGIES: dict[str, str] = {
    "clarity": "Simplify sentence structure. Use short declarative sentences (under 15 words). Replace abstract claims with one concrete number or specific example. Remove jargon.",
    "value_proposition": "Lead with the strongest measurable outcome (score improvement, time saved, success rate). Make the unique benefit obvious in the first sentence.",
    "call_to_action": "Make the CTA specific and action-oriented. Replace generic CTAs ('Learn More') with benefit-driven ones ('Start Your 200-Point Plan'). Match CTA to the campaign goal.",
    "brand_voice": "Say 'your child' NOT 'your student'. Say 'SAT tutoring' NOT 'SAT prep'. Say 'raise your child's score' NOT 'unlock potential'. Lead with outcomes (what the child gains), not features (what we offer). Use specific numbers ('200+ points', '3.4 million sessions') instead of vague adjectives. Use plain, direct speech — no marketing jargon. NEVER use as empty adjectives: personalized, expert, data-driven, tailored, custom. Remove any forbidden words.",
    "emotional_resonance": "Add a specific, relatable scenario the audience would recognize. Use second person ('your child') and reference a real pain point or aspiration from the brief's audience description.",
}


def _is_validation_error(error: str | None) -> bool:
    """True if the error string describes a Pydantic validation failure (length, word count, etc.)."""
    if not error:
        return False
    err_lower = error.lower()
    return any(kw in err_lower for kw in [
        "string_too_long", "too long", "characters", "word count", "5-8 words",
        "validation error for adcopy", "value_error",
    ])


def _build_validation_fix_prompt(current_ad: "AdCopy", error: str) -> str:
    """
    Build a short, targeted prompt to fix validation errors (length, word count).

    Unlike build_regeneration_prompt() which is designed for quality improvement,
    this produces a minimal instruction to fix a mechanical constraint violation.
    """
    ad_block = json.dumps(current_ad.model_dump(), indent=2)
    fix_instructions = []
    err_lower = error.lower()
    if "primary_text" in err_lower and ("too long" in err_lower or "500" in err_lower or "string_too_long" in err_lower):
        fix_instructions.append(
            "primary_text exceeds 500 characters. Shorten it to under 500 characters. "
            "Cut the weakest sentence — keep the hook and CTA intact."
        )
    if "image_prompt" in err_lower and ("too long" in err_lower or "450" in err_lower or "string_too_long" in err_lower):
        fix_instructions.append(
            "image_prompt exceeds 450 characters. Shorten it to under 450 characters. "
            "Keep the scene description and emotional tone."
        )
    if "headline" in err_lower and ("word" in err_lower or "5-8" in err_lower):
        fix_instructions.append(
            "headline must be exactly 5-8 words. Rewrite it to be 5-8 words "
            "while keeping the same benefit."
        )
    if not fix_instructions:
        return ""  # Not a fixable validation error — caller should use full regen
    fixes = "\n".join(f"- {f}" for f in fix_instructions)
    return f"""Fix the validation errors listed below. Change ONLY the fields that need fixing.
Keep all other fields exactly the same.

Errors to fix:
{fixes}

Current ad:
{ad_block}

Return ONLY valid JSON with all 5 fields (primary_text, headline, description, cta_button, image_prompt). No markdown."""


def _is_schema_validation_draft_error(error: str | None) -> bool:
    """True if draft failed due to schema/validation (recoverable by retry or regen)."""
    if not error:
        return False
    err_lower = error.lower()
    return "schema validation failed" in err_lower or "json parse failed" in err_lower


def _minimal_ad_from_raw(raw_draft: dict, validation_errors: list) -> AdCopy | None:
    """
    Build a valid AdCopy from raw_draft by replacing failed fields with GOLD_ANCHOR values.
    Used so we can pass a current_ad into the regen path with the validation error as rationale.
    """
    if not raw_draft or not isinstance(raw_draft, dict):
        return None
    minimal = dict(GOLD_ANCHOR)
    minimal.update({k: v for k, v in raw_draft.items() if k in minimal})
    failed_fields = set()
    for err in validation_errors or []:
        loc = err.get("loc") or ()
        if loc and isinstance(loc, (list, tuple)) and len(loc) > 0:
            field = loc[0]
            if field in GOLD_ANCHOR:
                failed_fields.add(field)
    for field in failed_fields:
        minimal[field] = GOLD_ANCHOR[field]
    try:
        return AdCopy.model_validate(minimal)
    except Exception:
        return None


def _is_judge_transient_error(error: str | None) -> bool:
    """True if judge failed due to timeout or connection (retry once)."""
    if not error:
        return False
    err_lower = error.lower()
    return (
        "timed out" in err_lower
        or "timeout" in err_lower
        or "interrupted" in err_lower
        or "connection" in err_lower
        or "request cancelled" in err_lower
    )


def _editor_regen(drafter: AdDrafter, regen_prompt: str) -> dict[str, Any]:
    """
    Call Gemini with editor JSON prompt; parse optimized_ad; validate as AdCopy.

    Args:
        drafter: AdDrafter instance (uses _call_gemini, _clean_json_response).
        regen_prompt: Full prompt string.

    Returns:
        dict: success, data (AdCopy if success), error, changes_made (list).
    """
    parsed: dict | None = None
    last_regen_exc: Exception | None = None
    for regen_attempt in range(2):
        try:
            raw = drafter._call_gemini(
                regen_prompt,
                drafter._model_name,
                {"temperature": 0.7, "response_mime_type": "application/json"},
            )
            cleaned = drafter._clean_json_response(raw)
            parsed = json.loads(cleaned)
            break
        except Exception as e:
            last_regen_exc = e
            if regen_attempt == 0 and ("504" in str(e) or "Deadline Exceeded" in str(e)):
                continue
            return {
                "success": False,
                "data": None,
                "error": str(e),
                "changes_made": [],
            }
    if parsed is None:
        return {
            "success": False,
            "data": None,
            "error": str(last_regen_exc) if last_regen_exc else "Regen parse failed",
            "changes_made": [],
        }
    try:
        if "optimized_ad" in parsed:
            ad = AdCopy.model_validate(parsed["optimized_ad"])
            changes = parsed.get("changes_made") or []
        else:
            ad = AdCopy.model_validate(parsed)
            changes = []
        return {"success": True, "data": ad, "error": None, "changes_made": changes}
    except PydanticValidationError as ve:
        return {"success": False, "data": None, "error": str(ve), "changes_made": []}


REASONABLE_RATIONALE_MAX_CHARS_MULTI: int = 120


def _get_weak_and_strong_dimensions(report: EvaluationReport) -> tuple[list[str], list[str]]:
    """
    Split dimensions into weak (score < QUALITY_THRESHOLD) and strong (score >= STRONG_DIMENSION_THRESHOLD).

    Returns:
        (weak_list, strong_list) for use in surgical regeneration prompt.
    """
    weak: list[str] = []
    strong: list[str] = []
    for dim in DIMENSIONS:
        ds = getattr(report, dim, None)
        if ds is None or not hasattr(ds, "score"):
            continue
        s = float(ds.score)
        if s < QUALITY_THRESHOLD:
            weak.append(dim)
        elif s >= STRONG_DIMENSION_THRESHOLD:
            strong.append(dim)
    return weak, strong


def _get_guideline_slice(brand_guidelines: dict, keys: list[str]) -> str:
    """Get a nested value from brand_guidelines by key path. Returns JSON string or empty."""
    cur = brand_guidelines
    for k in keys:
        cur = cur.get(k) if isinstance(cur, dict) else None
        if cur is None:
            return ""
    return json.dumps(cur, indent=2) if cur is not None else ""


def build_regeneration_prompt(
    current_ad: AdCopy,
    brand_guidelines: dict,
    brief_goal: str,
    brief_hook_type: str,
    *,
    report: EvaluationReport | None = None,
    single_weak_dimension: str | None = None,
    single_rationale: str | None = None,
    brief_audience: str = "",
    brief_tone: str = "",
) -> str:
    """
    Build a surgical regeneration prompt: targeted optimizations on failed dimensions only.

    When report is provided: uses all weak dimensions (score < 7) and strong dimensions (>= 8)
    with chained "Required Fixes" and explicit preservation. When report is None (e.g. scan
    failure): uses single_weak_dimension and single_rationale.

    Returns a prompt that asks for JSON: {"optimized_ad": {...}, "changes_made": [{"dimension": "...", "action": "..."}]}.

    Args:
        current_ad: The failed ad to fix.
        brand_guidelines: Full dict; slices per dimension used.
        brief_goal: "awareness" or "conversion".
        brief_hook_type: So the fix does not break the original hook.
        report: Full EvaluationReport when available; used to derive weak/strong and rationales.
        single_weak_dimension: Used when report is None (e.g. scan fail).
        single_rationale: Judge or scan rationale when report is None.
        brief_audience: Target audience description from the brief.
        brief_tone: Tone direction from the brief.

    Returns:
        str: Prompt string for the drafter.
    """
    ad_block = json.dumps(current_ad.model_dump(), indent=2)
    audience_line = f"TARGET AUDIENCE: {brief_audience}" if brief_audience else ""
    tone_line = f"REQUIRED TONE: {brief_tone}" if brief_tone else ""
    context_line = f"BRIEF CONTEXT (do not change): goal={brief_goal}, hook_type={brief_hook_type}. CTA must still match goal."

    if report is not None:
        weak_dims, strong_dims = _get_weak_and_strong_dimensions(report)
        # If no weak dims (edge case), fall back to single weakest
        if not weak_dims:
            weak_dims = [report.weakest_dimension]
        max_rationale = REASONABLE_RATIONALE_MAX_CHARS_MULTI if len(weak_dims) > 1 else REASONABLE_RATIONALE_MAX_CHARS
        required_fixes: list[str] = []
        for dim in weak_dims:
            ds = getattr(report, dim, None)
            score = getattr(ds, "score", 0) if ds else 0
            rationale = (getattr(ds, "rationale", "") or "")[:max_rationale].strip()
            keys = DIMENSION_TO_GUIDELINE_KEY.get(dim, [])
            guideline_slice = _get_guideline_slice(brand_guidelines, keys)
            display = DIMENSION_DISPLAY_NAMES.get(dim, dim)
            strategy = DIMENSION_FIX_STRATEGIES.get(dim, "")
            fix_block = f"For {display} (scored {score:.1f}/10, needs 7.0): Judge feedback — {rationale}"
            if strategy:
                fix_block += f". FIX STRATEGY: {strategy}"
            if guideline_slice:
                fix_block += f". Brand rules: {guideline_slice[:300]}"
            required_fixes.append(fix_block)
        preserve_line = ""
        if strong_dims:
            strong_names = [DIMENSION_DISPLAY_NAMES.get(d, d) for d in strong_dims]
            preserve_line = f"Do not change the following (they scored 8 or higher): {', '.join(strong_names)}."
        required_section = "\n".join(f"• {f}" for f in required_fixes)
        voice = (brand_guidelines or {}).get("voice") or {}
        forbidden_list = voice.get("forbidden_words_and_phrases") or []
        forbidden_line = "\n• FORBIDDEN — do not use these words/phrases in optimized_ad: " + ", ".join(f'"{w}"' for w in forbidden_list) + "." if forbidden_list else ""
        return f"""CRITICAL: primary_text must be at most 500 characters. image_prompt must be at most 450 characters. Exceeding these limits will reject the ad.

Act as a Senior Ad Copy Editor. Your job is to perform Targeted Optimizations on failed ad drafts.

The ad FAILED because every dimension must score >= 7.0. Current average: {report.average_score:.1f}/10.

{audience_line}
{tone_line}
{context_line}

Inputs:
1) The Original Ad Copy (below).
2) Scores with specific fix strategies for each weak dimension.
3) Weak dimensions (score < 7) to fix: {', '.join(DIMENSION_DISPLAY_NAMES.get(d, d) for d in weak_dims)}.

Constraints:
• Preservation: Do NOT change dimensions that scored 8 or higher.
• Fixation: Focus 100% of your creative energy on rewriting only the specific Weak Dimensions.
• Lengths: primary_text at most 500 characters, hook sentence must end with . ? or ! before character 100; headline 5-8 words; image_prompt at most 450 characters.{forbidden_line}
• JSON Output: Return a single JSON object with "optimized_ad" (same 5 fields) and "changes_made" (list of {{"dimension": "<display name>", "action": "<short description of what you changed>"}}).

CURRENT AD:
{ad_block}

Required Fixes:
{required_section}
{chr(10) + preserve_line if preserve_line else ""}

Return valid JSON only, with this exact structure:
{{"optimized_ad": {{ "primary_text": "...", "headline": "...", "description": "...", "cta_button": "...", "image_prompt": "..." }}, "changes_made": [{{"dimension": "Value Prop", "action": "Added 200+ point stat"}}, ...]}}
"""

    # Scan-fail or no report: single dimension
    dim = single_weak_dimension or "brand_voice"
    rationale = (single_rationale or "")[:REASONABLE_RATIONALE_MAX_CHARS].strip()
    keys = DIMENSION_TO_GUIDELINE_KEY.get(dim, [])
    guideline_slice = _get_guideline_slice(brand_guidelines, keys)
    display = DIMENSION_DISPLAY_NAMES.get(dim, dim)
    strategy = DIMENSION_FIX_STRATEGIES.get(dim, "")
    voice = (brand_guidelines or {}).get("voice") or {}
    forbidden_list = voice.get("forbidden_words_and_phrases") or []
    forbidden_line = "\n• FORBIDDEN — do not use these words/phrases in optimized_ad: " + ", ".join(f'"{w}"' for w in forbidden_list) + "." if forbidden_list else ""
    strategy_line = f"\nFIX STRATEGY: {strategy}" if strategy else ""
    return f"""CRITICAL: primary_text must be at most 500 characters. image_prompt must be at most 450 characters. Exceeding these limits will reject the ad.

Act as a Senior Ad Copy Editor. Your job is to perform Targeted Optimizations on failed ad drafts.

{audience_line}
{tone_line}
{context_line}

Inputs:
1) The Original Ad Copy (below).
2) Weak dimension to fix: {display}.
3) Feedback: {rationale}{strategy_line}

Constraints:
• Fixation: Focus 100% on rewriting only the parts that affect {display}.{forbidden_line}
• Lengths: primary_text at most 500 characters, hook sentence must end with . ? or ! before character 100; headline 5-8 words; image_prompt at most 450 characters.
• JSON Output: Return a single JSON object with "optimized_ad" (same 5 fields) and "changes_made" (list of {{"dimension": "<name>", "action": "<short description>"}}).

CURRENT AD:
{ad_block}

Relevant brand rules for this dimension:
{guideline_slice if guideline_slice else "None specified."}

Return valid JSON only:
{{"optimized_ad": {{ "primary_text": "...", "headline": "...", "description": "...", "cta_button": "...", "image_prompt": "..." }}, "changes_made": [{{"dimension": "{display}", "action": "..."}}]}}
"""


def run_brief(
    brief: AdBrief,
    competitive_context: dict,
    brand_guidelines: dict,
    variation_index: int = 0,
    seed: int = DEFAULT_SEED,
    total_variations: int = 5,
) -> dict[str, Any]:
    """
    Run draft → validate/scan repairs (capped) → judge → iterate for one brief variation.

    Evaluation cycle N (logged as cycle=N) is assigned only after the Nth successful judge call.
    Pre-judge schema/validation/safety issues are repaired with at most
    MAX_PRE_JUDGE_REPAIR_ATTEMPTS editor regenerations (no judge, no iteration_log row).

    Args:
        brief: Validated AdBrief.
        competitive_context: Loaded competitive_context.json.
        brand_guidelines: Loaded brand_guidelines.json (used for forbidden phrases and regen slice).
        variation_index: Index of this variation (0..total_variations-1).
        seed: Deterministic seed (typically DEFAULT_SEED + variation_index).
        total_variations: Total number of variations per brief (for drafter diversity instruction).

    Returns:
        dict: brief_id, variation_index, status (published|unresolvable), cycles_used,
              final_ad, final_score, final_report, iteration_log, model_used, tokens_used,
              estimated_cost_usd, error.
    """
    # Gates 1 & 2 — before any API call
    guard_result = validate_free_text(brief)
    if not guard_result.get("success", True):
        return {
            "brief_id": brief.id,
            "variation_index": variation_index,
            "status": "unresolvable",
            "cycles_used": 0,
            "final_ad": None,
            "final_score": None,
            "final_report": None,
            "iteration_log": [],
            "changes_made": [],
            "model_used": None,
            "tokens_used": 0,
            "estimated_cost_usd": 0.0,
            "error": guard_result.get("error", "Guardrails rejected"),
        }

    for field_name, value in brief.model_dump().items():
        sanitized = sanitize_for_injection(str(value), field_name)
        if not sanitized.get("success", True):
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "unresolvable",
                "cycles_used": 0,
                "final_ad": None,
                "final_score": None,
                "final_report": None,
                "iteration_log": [],
                "changes_made": [],
                "model_used": None,
                "tokens_used": 0,
                "estimated_cost_usd": 0.0,
                "error": sanitized.get("error", "Injection detected"),
            }

    forbidden_phrases = None
    if isinstance(brand_guidelines, dict):
        voice = brand_guidelines.get("voice") or {}
        if isinstance(voice, dict):
            forbidden_phrases = voice.get("forbidden_words_and_phrases")

    drafter = AdDrafter()
    judge = AdJudge()
    iteration_log: list[dict] = []
    last_changes_made: list[dict[str, str]] = []
    current_ad: AdCopy | None = None
    current_report: EvaluationReport | None = None
    evaluation_cycles_completed: int = 0
    pre_judge_repairs_used: int = 0
    total_tokens = 0
    model_used: str | None = None
    total_cost = 0.0

    _tag = f"{brief.id} v{variation_index}"

    def _dbg(msg: str) -> None:
        """Print a debug line tagged with brief+variation."""
        print(f"  [{_tag}] {msg}", flush=True)

    # Cost estimation (same logic as main.py so we can sum later)
    def _estimate_cost(tokens: int, model: str | None) -> float:
        if not model:
            return 0.0
        m = model.lower()
        if "gemini" in m:
            return (tokens / 1000) * 0.000075
        if "claude" in m:
            return (tokens / 1000) * 0.003
        return 0.0

    def _regen_cost_update() -> None:
        nonlocal total_tokens, total_cost
        total_tokens += 500
        total_cost += _estimate_cost(500, drafter._model_name)

    def acquire_valid_safe_ad(post_judge_regen_prompt: str | None) -> tuple[bool, str | None]:
        """
        Set current_ad to schema-valid AdCopy passing scan_output_safety.

        Pre-judge repairs (schema/safety/regen validation) consume MAX_PRE_JUDGE_REPAIR_ATTEMPTS
        total per variation. Post-judge regen prompt runs first when provided (quality iteration;
        if it fails, repairs use the same pre-judge budget).

        Returns:
            (True, None) on success, or (False, error_message).
        """
        nonlocal current_ad, last_changes_made, pre_judge_repairs_used, model_used, total_tokens, total_cost

        draft_retries_no_minimal = 0

        if post_judge_regen_prompt is not None:
            rr = _editor_regen(drafter, post_judge_regen_prompt)
            _regen_cost_update()
            if rr.get("success"):
                current_ad = rr.get("data")
                last_changes_made = list(rr.get("changes_made") or [])
            else:
                rationale = (rr.get("error") or "Judge-guided regen failed").strip()
                fixed = False
                while not fixed:
                    if pre_judge_repairs_used >= MAX_PRE_JUDGE_REPAIR_ATTEMPTS:
                        return False, f"pre_judge_repair_exhausted:{rationale}"
                    pre_judge_repairs_used += 1
                    base = current_ad
                    if base is None:
                        return False, rationale
                    # Use targeted fix for validation errors, full regen for others
                    rp = _build_validation_fix_prompt(base, rationale) if _is_validation_error(rationale) else ""
                    if not rp:
                        rp = build_regeneration_prompt(
                            base,
                            brand_guidelines,
                            brief.goal,
                            brief.hook_type,
                            single_weak_dimension="brand_voice",
                            single_rationale=rationale,
                            brief_audience=brief.audience,
                            brief_tone=brief.tone,
                        )
                    rr2 = _editor_regen(drafter, rp)
                    _regen_cost_update()
                    if rr2.get("success"):
                        current_ad = rr2.get("data")
                        last_changes_made = list(rr2.get("changes_made") or [])
                        fixed = True
                    else:
                        rationale = (rr2.get("error") or rationale).strip()

        while True:
            if current_ad is None:
                draft_result = drafter.draft_ad(
                    brief,
                    competitive_context,
                    brand_guidelines,
                    seed=seed,
                    variation_index=variation_index,
                    total_variations=total_variations,
                )
                if not draft_result.get("success"):
                    err = draft_result.get("error")
                    if not err:
                        err = "Draft failed (primary and fallback exhausted or validation failed)."
                    _dbg(f"DRAFT FAILED: {err}")
                    if _is_schema_validation_draft_error(err):
                        raw_draft = draft_result.get("raw_draft")
                        validation_errors = draft_result.get("validation_errors") or []
                        minimal_ad = _minimal_ad_from_raw(raw_draft, validation_errors) if raw_draft else None
                        if minimal_ad is None:
                            draft_retries_no_minimal += 1
                            if draft_retries_no_minimal > MAX_DRAFT_RETRIES_NO_MINIMAL:
                                return False, f"schema_validation_exhausted:{err}"
                            continue
                        if pre_judge_repairs_used >= MAX_PRE_JUDGE_REPAIR_ATTEMPTS:
                            return False, f"schema_validation_exhausted:{err}"
                        pre_judge_repairs_used += 1
                        # Use targeted fix for validation errors, full regen for others
                        regen_prompt = _build_validation_fix_prompt(minimal_ad, err) if _is_validation_error(err) else ""
                        if not regen_prompt:
                            regen_prompt = build_regeneration_prompt(
                                minimal_ad,
                                brand_guidelines,
                                brief.goal,
                                brief.hook_type,
                                single_weak_dimension="brand_voice",
                                single_rationale=err,
                                brief_audience=brief.audience,
                                brief_tone=brief.tone,
                            )
                        rr = _editor_regen(drafter, regen_prompt)
                        _regen_cost_update()
                        if not rr.get("success"):
                            current_ad = None
                            continue
                        current_ad = rr.get("data")
                        last_changes_made = list(rr.get("changes_made") or [])
                    else:
                        mu = draft_result.get("model_used")
                        if mu is not None and not isinstance(mu, str):
                            mu = None
                        model_used = mu or model_used
                        return False, err
                else:
                    current_ad = draft_result.get("data")
                    total_tokens += draft_result.get("tokens_used", 0)
                    model_used = draft_result.get("model_used") or model_used
                    total_cost += _estimate_cost(draft_result.get("tokens_used", 0), model_used)
                    _dbg(f"DRAFT OK: primary_text={len(getattr(current_ad, 'primary_text', '') or '')}ch, "
                         f"headline={len((getattr(current_ad, 'headline', '') or '').split())}w, "
                         f"image_prompt={len(getattr(current_ad, 'image_prompt', '') or '')}ch")

            scan_result = scan_output_safety(current_ad, forbidden_phrases=forbidden_phrases)
            if scan_result.get("safe", True):
                _dbg("SAFETY SCAN: passed")
                return True, None

            rationale = (scan_result.get("error") or "Safety violations.").strip()
            _dbg(f"SAFETY SCAN FAILED: {rationale}")
            fixed_scan = False
            while not fixed_scan:
                if pre_judge_repairs_used >= MAX_PRE_JUDGE_REPAIR_ATTEMPTS:
                    return False, f"safety_failure_exhausted:{rationale}"
                pre_judge_repairs_used += 1
                rp = build_regeneration_prompt(
                    current_ad,
                    brand_guidelines,
                    brief.goal,
                    brief.hook_type,
                    single_weak_dimension="brand_voice",
                    single_rationale=rationale,
                    brief_audience=brief.audience,
                    brief_tone=brief.tone,
                )
                rr = _editor_regen(drafter, rp)
                _regen_cost_update()
                if rr.get("success"):
                    current_ad = rr.get("data")
                    last_changes_made = list(rr.get("changes_made") or [])
                    fixed_scan = True
                else:
                    rationale = (rr.get("error") or rationale).strip()

    while evaluation_cycles_completed < MAX_EVALUATION_CYCLES:
        if evaluation_cycles_completed == 0:
            ok, acq_err = acquire_valid_safe_ad(None)
        else:
            _dbg(f"REGEN: weakest={current_report.weakest_dimension}, rebuilding ad...")
            pjg = build_regeneration_prompt(
                current_ad,
                brand_guidelines,
                brief.goal,
                brief.hook_type,
                report=current_report,
                brief_audience=brief.audience,
                brief_tone=brief.tone,
            )
            ok, acq_err = acquire_valid_safe_ad(pjg)

        if not ok:
            _dbg(f"ACQUIRE FAILED at cycle {evaluation_cycles_completed}: {acq_err}")
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "unresolvable",
                "cycles_used": evaluation_cycles_completed,
                "final_ad": None,
                "final_score": None,
                "final_report": None,
                "iteration_log": iteration_log,
                "changes_made": last_changes_made,
                "model_used": model_used,
                "tokens_used": total_tokens,
                "estimated_cost_usd": total_cost,
                "error": acq_err or "acquire_valid_safe_ad_failed",
            }

        evaluation_cycles_completed += 1
        ev_cycle_num = evaluation_cycles_completed

        judge_result = None
        last_judge_err = None
        for judge_attempt in range(2):
            judge_result = judge.evaluate_ad(current_ad)
            if judge_result.get("success"):
                break
            last_judge_err = judge_result.get("error", "Judge failed")
            if judge_attempt == 0 and _is_judge_transient_error(last_judge_err):
                continue
            break
        if not judge_result or not judge_result.get("success"):
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "unresolvable",
                "cycles_used": evaluation_cycles_completed,
                "final_ad": current_ad,
                "final_score": None,
                "final_report": None,
                "iteration_log": iteration_log,
                "changes_made": last_changes_made,
                "model_used": model_used,
                "tokens_used": total_tokens,
                "estimated_cost_usd": total_cost,
                "error": judge_result.get("error", last_judge_err) if judge_result else (last_judge_err or "Judge failed"),
            }

        report = judge_result.get("data")
        if report is not None and not isinstance(report, EvaluationReport):
            try:
                report = EvaluationReport.model_validate(report)
            except Exception:
                return {
                    "brief_id": brief.id,
                    "variation_index": variation_index,
                    "status": "unresolvable",
                    "cycles_used": evaluation_cycles_completed,
                    "final_ad": current_ad,
                    "final_score": None,
                    "final_report": None,
                    "iteration_log": iteration_log,
                    "changes_made": last_changes_made,
                    "model_used": model_used,
                    "tokens_used": total_tokens,
                    "estimated_cost_usd": total_cost,
                    "error": "Judge returned data that is not a valid EvaluationReport",
                }
        if report is None:
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "unresolvable",
                "cycles_used": evaluation_cycles_completed,
                "final_ad": current_ad,
                "final_score": None,
                "final_report": None,
                "iteration_log": iteration_log,
                "changes_made": last_changes_made,
                "model_used": model_used,
                "tokens_used": total_tokens,
                "estimated_cost_usd": total_cost,
                "error": "Judge succeeded but returned no report data",
            }
        current_report = report
        total_tokens += 1500
        total_cost += _estimate_cost(1500, getattr(judge, "_model_name", "claude-sonnet-4-5"))

        # Debug: show all dimension scores for this cycle
        _scores = {
            "clarity": getattr(getattr(report, "clarity", None), "score", "?"),
            "value_prop": getattr(getattr(report, "value_proposition", None), "score", "?"),
            "cta": getattr(getattr(report, "call_to_action", None), "score", "?"),
            "brand_voice": getattr(getattr(report, "brand_voice", None), "score", "?"),
            "emotional": getattr(getattr(report, "emotional_resonance", None), "score", "?"),
        }
        _fails = [f"{k}={v}" for k, v in _scores.items() if isinstance(v, (int, float)) and v < 7.0]
        _dbg(f"JUDGE cycle {ev_cycle_num}: avg={report.average_score:.1f} | "
             f"{' | '.join(f'{k}={v}' for k, v in _scores.items())}"
             f"{' | BELOW 7: ' + ', '.join(_fails) if _fails else ' | ALL PASS'}")

        def _dim_score(name: str) -> float | None:
            ds = getattr(report, name, None)
            if ds is None or not hasattr(ds, "score"):
                return None
            return round(float(ds.score), 1)

        log_entry: dict[str, Any] = {
            "cycle": ev_cycle_num,
            "primary_text": getattr(current_ad, "primary_text", "") or "",
            "headline": getattr(current_ad, "headline", "") or "",
            "cta_button": getattr(current_ad, "cta_button", "") or "",
            "description": getattr(current_ad, "description", "") or "",
            "clarity": _dim_score("clarity"),
            "value_proposition": _dim_score("value_proposition"),
            "call_to_action": _dim_score("call_to_action"),
            "brand_voice": _dim_score("brand_voice"),
            "emotional_resonance": _dim_score("emotional_resonance"),
            "average_score": report.average_score,
            "weakest_dimension": report.weakest_dimension,
            "status": "published" if report.passes_threshold else "below_threshold",
        }
        if last_changes_made:
            log_entry["changes_made"] = last_changes_made
        iteration_log.append(log_entry)

        if report.passes_threshold:
            _dbg(f"PUBLISHED at cycle {ev_cycle_num}: avg={report.average_score:.1f}")
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "published",
                "cycles_used": evaluation_cycles_completed,
                "final_ad": current_ad,
                "final_score": report.average_score,
                "final_report": report,
                "iteration_log": iteration_log,
                "changes_made": last_changes_made,
                "model_used": model_used,
                "tokens_used": total_tokens,
                "estimated_cost_usd": total_cost,
                "error": None,
            }

        if evaluation_cycles_completed >= MAX_EVALUATION_CYCLES:
            _dbg(f"EXHAUSTED {MAX_EVALUATION_CYCLES} cycles: avg={report.average_score:.1f}, "
                 f"weakest={report.weakest_dimension}")
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "unresolvable",
                "cycles_used": evaluation_cycles_completed,
                "final_ad": None,
                "final_score": report.average_score,
                "final_report": report,
                "iteration_log": iteration_log,
                "changes_made": last_changes_made,
                "model_used": model_used,
                "tokens_used": total_tokens,
                "estimated_cost_usd": total_cost,
                "error": None,
            }

    return {
        "brief_id": brief.id,
        "variation_index": variation_index,
        "status": "unresolvable",
        "cycles_used": evaluation_cycles_completed,
        "final_ad": None,
        "final_score": None,
        "final_report": None,
        "iteration_log": iteration_log,
        "changes_made": last_changes_made,
        "model_used": model_used,
        "tokens_used": total_tokens,
        "estimated_cost_usd": total_cost,
        "error": "max_evaluation_cycles_reached",
    }
