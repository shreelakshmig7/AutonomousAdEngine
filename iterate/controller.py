"""
controller.py
-------------
Varsity Ad Engine — Nerdy / Gauntlet — Iteration controller (PR4)
-------------------------------------------------------------------
run_brief() orchestrates draft → scan → judge → iterate. build_regeneration_prompt()
uses a surgical Senior Ad Copy Editor persona: targeted optimizations on weak
dimensions only, preservation of dimensions scoring >= 8, JSON output with
optimized_ad and changes_made. Gates 1–2 run before calling drafter.

Key constants / functions:
  DIMENSION_TO_GUIDELINE_KEY — map dimension to brand_guidelines slice
  run_brief()               — full cycle; returns changes_made from last regen
  build_regeneration_prompt() — surgical multi-dimension regen prompt
"""

from __future__ import annotations

import json
from typing import Any

from evaluate.rubrics import (
    AdBrief,
    AdCopy,
    DIMENSION_DISPLAY_NAMES,
    DIMENSIONS,
    EvaluationReport,
    MAX_CYCLES,
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

    Returns:
        str: Prompt string for the drafter.
    """
    ad_block = json.dumps(current_ad.model_dump(), indent=2)
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
            rationale = (getattr(ds, "rationale", "") or "")[:max_rationale].strip()
            keys = DIMENSION_TO_GUIDELINE_KEY.get(dim, [])
            guideline_slice = _get_guideline_slice(brand_guidelines, keys)
            display = DIMENSION_DISPLAY_NAMES.get(dim, dim)
            fix_block = f"For {display}: Judge feedback — {rationale}"
            if guideline_slice:
                fix_block += f". Use brand rules: {guideline_slice[:300]}"
            required_fixes.append(fix_block)
        preserve_line = ""
        if strong_dims:
            strong_names = [DIMENSION_DISPLAY_NAMES.get(d, d) for d in strong_dims]
            preserve_line = f"Do not change the following (they scored 8 or higher): {', '.join(strong_names)}."
        required_section = "\n".join(f"• {f}" for f in required_fixes)
        return f"""Act as a Senior Ad Copy Editor. Your job is to perform Targeted Optimizations on failed ad drafts.

Inputs:
1) The Original Ad Copy (below).
2) Scores and rationales: the ad failed on the dimension(s) listed under Required Fixes.
3) Weak dimensions (score < 7) to fix: {', '.join(DIMENSION_DISPLAY_NAMES.get(d, d) for d in weak_dims)}.

Constraints:
• Preservation: Do NOT change dimensions that scored 8 or higher.
• Fixation: Focus 100% of your creative energy on rewriting only the specific Weak Dimensions.
• JSON Output: Return a single JSON object with "optimized_ad" (same 5 fields) and "changes_made" (list of {{"dimension": "<display name>", "action": "<short description of what you changed>"}}).

{context_line}

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
    return f"""Act as a Senior Ad Copy Editor. Your job is to perform Targeted Optimizations on failed ad drafts.

Inputs:
1) The Original Ad Copy (below).
2) Weak dimension to fix: {display}.
3) Feedback: {rationale}

Constraints:
• Fixation: Focus 100% on rewriting only the parts that affect {display}.
• JSON Output: Return a single JSON object with "optimized_ad" (same 5 fields) and "changes_made" (list of {{"dimension": "<name>", "action": "<short description>"}}).

{context_line}

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
    Run the full draft → scan → judge → iterate cycle for one brief variation.

    Gates: (1) validate_free_text, (2) sanitize_for_injection, (3) draft_ad,
    (4) scan_output_safety, (5) evaluate_ad, (6) passes_threshold check.
    On scan failure: treat as failed cycle; regenerate targeting brand_voice; cap at MAX_CYCLES.

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
    scan_fail_rationale: str = ""  # when scan fails, pass this as regen rationale
    cycle = 0
    total_tokens = 0
    model_used: str | None = None
    total_cost = 0.0

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

    while cycle < MAX_CYCLES:
        cycle += 1

        if current_ad is None:
            # First cycle: full draft from brief
            draft_result = drafter.draft_ad(
                brief,
                competitive_context,
                brand_guidelines,
                seed=seed,
                variation_index=variation_index,
                total_variations=total_variations,
            )
            if not draft_result.get("success"):
                # Never swallow draft failure: explicit error; model_used must be str or None (no NaN)
                err = draft_result.get("error")
                if not err:
                    err = "Draft failed (primary and fallback exhausted or validation failed)."
                mu = draft_result.get("model_used")
                if mu is not None and not isinstance(mu, str):
                    mu = None
                return {
                    "brief_id": brief.id,
                    "variation_index": variation_index,
                    "status": "unresolvable",
                    "cycles_used": cycle,
                    "final_ad": None,
                    "final_score": None,
                    "final_report": None,
                    "iteration_log": iteration_log,
                    "changes_made": last_changes_made,
                    "model_used": mu,
                    "tokens_used": total_tokens,
                    "estimated_cost_usd": total_cost,
                    "error": err,
                }
            current_ad = draft_result.get("data")
            total_tokens += draft_result.get("tokens_used", 0)
            model_used = draft_result.get("model_used") or model_used
            total_cost += _estimate_cost(draft_result.get("tokens_used", 0), model_used)
        else:
            # Regen cycle: surgical prompt and parse optimized_ad + changes_made
            if current_report is not None:
                regen_prompt = build_regeneration_prompt(
                    current_ad,
                    brand_guidelines,
                    brief.goal,
                    brief.hook_type,
                    report=current_report,
                )
            else:
                weakest = "brand_voice"
                rationale = scan_fail_rationale
                regen_prompt = build_regeneration_prompt(
                    current_ad,
                    brand_guidelines,
                    brief.goal,
                    brief.hook_type,
                    single_weak_dimension=weakest,
                    single_rationale=rationale,
                )
            try:
                raw = drafter._call_gemini(regen_prompt, drafter._model_name, {"temperature": 0.7, "response_mime_type": "application/json"})
                cleaned = drafter._clean_json_response(raw)
                parsed = json.loads(cleaned)
                # Support wrapper {"optimized_ad": {...}, "changes_made": [...]} or legacy plain AdCopy
                if "optimized_ad" in parsed:
                    current_ad = AdCopy.model_validate(parsed["optimized_ad"])
                    last_changes_made = parsed.get("changes_made") or []
                else:
                    current_ad = AdCopy.model_validate(parsed)
                    last_changes_made = []
                total_tokens += 500  # approximate regen call
                total_cost += _estimate_cost(500, drafter._model_name)
            except Exception as e:
                return {
                    "brief_id": brief.id,
                    "variation_index": variation_index,
                    "status": "unresolvable",
                    "cycles_used": cycle,
                    "final_ad": None,
                    "final_score": None,
                    "final_report": None,
                    "iteration_log": iteration_log,
                    "changes_made": last_changes_made,
                    "model_used": model_used,
                    "tokens_used": total_tokens,
                    "estimated_cost_usd": total_cost,
                    "error": str(e),
                }

        if current_ad is None:
            break

        scan_result = scan_output_safety(current_ad, forbidden_phrases=forbidden_phrases)
        if not scan_result.get("safe", True):
            # Treat as failed cycle; regenerate targeting brand_voice with scan error as rationale
            scan_fail_rationale = scan_result.get("error", "Safety violations.")
            iteration_log.append({
                "cycle": cycle,
                "scan_failed": True,
                "error": scan_result.get("error"),
                "primary_text": getattr(current_ad, "primary_text", "") or "",
                "headline": getattr(current_ad, "headline", "") or "",
                "clarity": None,
                "value_proposition": None,
                "call_to_action": None,
                "brand_voice": None,
                "emotional_resonance": None,
                "average_score": None,
                "weakest_dimension": None,
                "status": "scan_failed",
            })
            if cycle >= MAX_CYCLES:
                return {
                    "brief_id": brief.id,
                    "variation_index": variation_index,
                    "status": "unresolvable",
                    "cycles_used": cycle,
                    "final_ad": None,
                    "final_score": None,
                    "final_report": None,
                    "iteration_log": iteration_log,
                    "changes_made": last_changes_made,
                    "model_used": model_used,
                    "tokens_used": total_tokens,
                    "estimated_cost_usd": total_cost,
                    "error": scan_result.get("error", "Safety violations"),
                }
            # Next iteration will use build_regeneration_prompt with single_weak_dimension=brand_voice
            current_report = None
            continue

        judge_result = judge.evaluate_ad(current_ad)
        if not judge_result.get("success"):
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "unresolvable",
                "cycles_used": cycle,
                "final_ad": current_ad,
                "final_score": None,
                "final_report": None,
                "iteration_log": iteration_log,
                "changes_made": last_changes_made,
                "model_used": model_used,
                "tokens_used": total_tokens,
                "estimated_cost_usd": total_cost,
                "error": judge_result.get("error", "Judge failed"),
            }

        report = judge_result.get("data")
        # Publish path must always attach an EvaluationReport instance (not dict/serialized).
        if report is not None and not isinstance(report, EvaluationReport):
            try:
                report = EvaluationReport.model_validate(report)
            except Exception:
                return {
                    "brief_id": brief.id,
                    "variation_index": variation_index,
                    "status": "unresolvable",
                    "cycles_used": cycle,
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
                "cycles_used": cycle,
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
        total_tokens += 1500  # approximate judge call
        total_cost += _estimate_cost(1500, getattr(judge, "_model_name", "claude-sonnet-4-5"))

        def _dim_score(name: str) -> float | None:
            ds = getattr(report, name, None)
            if ds is None or not hasattr(ds, "score"):
                return None
            return round(float(ds.score), 1)

        log_entry: dict[str, Any] = {
            "cycle": cycle,
            "primary_text": getattr(current_ad, "primary_text", "") or "",
            "headline": getattr(current_ad, "headline", "") or "",
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
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "published",
                "cycles_used": cycle,
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

        if cycle >= MAX_CYCLES:
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "unresolvable",
                "cycles_used": cycle,
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
        "cycles_used": cycle,
        "final_ad": None,
        "final_score": None,
        "final_report": None,
        "iteration_log": iteration_log,
        "changes_made": last_changes_made,
        "model_used": model_used,
        "tokens_used": total_tokens,
        "estimated_cost_usd": total_cost,
        "error": "Max cycles reached",
    }
