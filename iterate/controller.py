"""
controller.py
-------------
Varsity Ad Engine — Nerdy / Gauntlet — Iteration controller (PR4)
-------------------------------------------------------------------
AdController and run_brief() orchestrate draft → scan → judge → iterate.
build_regeneration_prompt() targets only weakest_dimension; <1000 tokens.
Gates 1–2 run in controller before calling drafter (defence in depth).

Key constants / functions:
  DIMENSION_TO_GUIDELINE_KEY — map dimension to brand_guidelines slice
  run_brief()               — full cycle for one brief variation
  build_regeneration_prompt() — regen prompt for targeted fix
"""

from __future__ import annotations

import json
from typing import Any

from evaluate.rubrics import (
    AdBrief,
    AdCopy,
    EvaluationReport,
    MAX_CYCLES,
    QUALITY_THRESHOLD,
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
    weakest_dimension: str,
    judge_rationale: str,
    brand_guidelines: dict,
    brief_goal: str,
    brief_hook_type: str,
) -> str:
    """
    Build a focused regeneration prompt targeting only the weakest dimension.
    Keeps prompt under 1000 tokens: no full brief, no cycle history, no competitive_context.

    Args:
        current_ad: The failed ad to fix.
        weakest_dimension: The one dimension to target.
        judge_rationale: One sentence from the judge (truncated to 200 chars).
        brand_guidelines: Full dict; only the slice for weakest_dimension is used.
        brief_goal: "awareness" or "conversion" (CTA must match).
        brief_hook_type: So the fix does not break the original hook.

    Returns:
        str: Prompt string for the drafter to produce a revised AdCopy.
    """
    rationale = (judge_rationale or "")[:REASONABLE_RATIONALE_MAX_CHARS].strip()
    keys = DIMENSION_TO_GUIDELINE_KEY.get(weakest_dimension, [])
    guideline_slice = _get_guideline_slice(brand_guidelines, keys)

    ad_block = json.dumps(current_ad.model_dump(), indent=2)

    return f"""You are revising existing Varsity Tutors ad copy. Fix ONLY the dimension that failed.

BRIEF CONTEXT (do not change): goal={brief_goal}, hook_type={brief_hook_type}. CTA must still match goal.

CURRENT AD (all 5 fields — preserve what works, change only what fixes the weak dimension):
{ad_block}

WEAK DIMENSION TO FIX: {weakest_dimension}
JUDGE FEEDBACK: {rationale}

RELEVANT BRAND RULES FOR THIS DIMENSION:
{guideline_slice if guideline_slice else "None specified."}

INSTRUCTIONS:
- Rewrite ONLY the parts of the ad that affect {weakest_dimension}.
- Keep primary_text, headline, description, cta_button, image_prompt structure.
- Do not change hook type or goal. Return valid JSON with exactly: primary_text, headline, description, cta_button, image_prompt.
"""


def run_brief(
    brief: AdBrief,
    competitive_context: dict,
    brand_guidelines: dict,
    variation_index: int = 0,
    seed: int = DEFAULT_SEED,
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
        variation_index: Index of this variation (0..VARIATIONS_PER_BRIEF-1).
        seed: Deterministic seed (typically DEFAULT_SEED + variation_index).

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
                brief, competitive_context, brand_guidelines, seed=seed
            )
            if not draft_result.get("success"):
                return {
                    "brief_id": brief.id,
                    "variation_index": variation_index,
                    "status": "unresolvable",
                    "cycles_used": cycle,
                    "final_ad": None,
                    "final_score": None,
                    "final_report": None,
                    "iteration_log": iteration_log,
                    "model_used": draft_result.get("model_used"),
                    "tokens_used": total_tokens,
                    "estimated_cost_usd": total_cost,
                    "error": draft_result.get("error", "Draft failed"),
                }
            current_ad = draft_result.get("data")
            total_tokens += draft_result.get("tokens_used", 0)
            model_used = draft_result.get("model_used") or model_used
            total_cost += _estimate_cost(draft_result.get("tokens_used", 0), model_used)
        else:
            # Regen cycle: build prompt and call drafter's LLM
            weakest = (current_report and getattr(current_report, "weakest_dimension", None)) or "brand_voice"
            if current_report and weakest:
                dim_score = getattr(current_report, weakest, None)
                rationale = getattr(dim_score, "rationale", "") if dim_score else ""
            else:
                rationale = scan_fail_rationale
            regen_prompt = build_regeneration_prompt(
                current_ad,
                weakest,
                rationale,
                brand_guidelines,
                brief.goal,
                brief.hook_type,
            )
            try:
                raw = drafter._call_gemini(regen_prompt, drafter._model_name, {"temperature": 0, "response_mime_type": "application/json"})
                cleaned = drafter._clean_json_response(raw)
                parsed = json.loads(cleaned)
                current_ad = AdCopy.model_validate(parsed)
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
                    "model_used": model_used,
                    "tokens_used": total_tokens,
                    "estimated_cost_usd": total_cost,
                    "error": scan_result.get("error", "Safety violations"),
                }
            # Next iteration will use build_regeneration_prompt with weakest_dimension=brand_voice, rationale=scan error
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
                "model_used": model_used,
                "tokens_used": total_tokens,
                "estimated_cost_usd": total_cost,
                "error": judge_result.get("error", "Judge failed"),
            }

        report = judge_result.get("data")
        current_report = report
        total_tokens += 1500  # approximate judge call
        total_cost += _estimate_cost(1500, getattr(judge, "_model_name", "claude-sonnet-4-5"))

        iteration_log.append({
            "cycle": cycle,
            "average_score": report.average_score if report else None,
            "weakest_dimension": report.weakest_dimension if report else None,
        })

        if report and report.passes_threshold:
            return {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "published",
                "cycles_used": cycle,
                "final_ad": current_ad,
                "final_score": report.average_score,
                "final_report": report,
                "iteration_log": iteration_log,
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
                "final_score": report.average_score if report else None,
                "final_report": report,
                "iteration_log": iteration_log,
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
        "model_used": model_used,
        "tokens_used": total_tokens,
        "estimated_cost_usd": total_cost,
        "error": "Max cycles reached",
    }
