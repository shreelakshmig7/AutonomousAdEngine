"""
main.py
-------
Varsity Ad Engine — Nerdy / Gauntlet — Pipeline entrypoint (PR4)
-----------------------------------------------------------------
run_pipeline_streaming() is a generator that yields progress for each
brief+variation; writes ads_library.json and iteration_log.csv.
Uses rich for CLI output. Does not crash if published < MIN_ADS_REQUIRED.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Generator

from evaluate.rubrics import QUALITY_THRESHOLD, MAX_CYCLES, AdBrief
from generate.prompts import DEFAULT_SEED
from iterate.controller import run_brief

# -----------------------------------------------------------------------------
# Constants (PR4 briefing — do not import MIN_ADS_REQUIRED from rubrics)
# -----------------------------------------------------------------------------
MIN_ADS_REQUIRED: int = 50
VARIATIONS_PER_BRIEF: int = 5
ADS_LIBRARY_PATH: str = "output/ads_library.json"
ITERATION_LOG_PATH: str = "output/iteration_log.csv"

# Cost estimation (PR4 briefing CORRECTION 8)
GEMINI_FLASH_COST_PER_1K_TOKENS: float = 0.000075
CLAUDE_SONNET_COST_PER_1K_TOKENS: float = 0.003


def estimate_cost(tokens: int, model: str | None) -> float:
    """
    Estimate USD cost for a given token count and model.

    Args:
        tokens: Estimated token count.
        model: Model name (e.g. gemini-2.5-flash, claude-sonnet-4-5).

    Returns:
        float: Estimated cost in USD.
    """
    if not model:
        return 0.0
    m = model.lower()
    if "gemini" in m:
        return (tokens / 1000) * GEMINI_FLASH_COST_PER_1K_TOKENS
    if "claude" in m:
        return (tokens / 1000) * CLAUDE_SONNET_COST_PER_1K_TOKENS
    return 0.0


def run_pipeline_streaming(
    briefs: list[AdBrief],
    competitive_context: dict,
    brand_guidelines: dict,
) -> Generator[dict[str, Any], None, None]:
    """
    Run the full pipeline for all briefs and variations; yield progress updates.

    For each brief × variation_index (0..VARIATIONS_PER_BRIEF-1) runs run_brief()
    with seed = DEFAULT_SEED + variation_index. Writes ads_library.json (published
    ads only) and iteration_log.csv. Final yield has status "complete" and aggregates.

    Args:
        briefs: List of validated AdBriefs.
        competitive_context: Loaded competitive_context.json.
        brand_guidelines: Loaded brand_guidelines.json.

    Yields:
        Progress dicts: brief_id, variation_index, status, cycle, score, weakest_dimension, message.
        Final dict: status="complete", total_briefs, total_variations, total_published,
                    total_unresolvable, avg_score, total_tokens, estimated_cost_usd.
    """
    ads_library: list[dict] = []
    iteration_rows: list[dict] = []
    total_published = 0
    total_unresolvable = 0
    total_tokens = 0
    total_cost = 0.0
    scores_for_avg: list[float] = []

    for brief in briefs:
        for variation_index in range(VARIATIONS_PER_BRIEF):
            seed = DEFAULT_SEED + variation_index
            yield {
                "brief_id": brief.id,
                "variation_index": variation_index,
                "status": "drafting",
                "cycle": 0,
                "score": None,
                "weakest_dimension": None,
                "message": f"Drafting {brief.id} variation {variation_index}",
            }

            result = run_brief(
                brief,
                competitive_context,
                brand_guidelines,
                variation_index=variation_index,
                seed=seed,
            )

            status = result.get("status", "unresolvable")
            cycles_used = result.get("cycles_used", 0)
            final_score = result.get("final_score")
            final_ad = result.get("final_ad")
            final_report = result.get("final_report")
            model_used = result.get("model_used", "")
            tokens_used = result.get("tokens_used", 0)
            cost_usd = result.get("estimated_cost_usd", 0.0)

            total_tokens += tokens_used
            total_cost += cost_usd

            weakest = None
            if final_report and hasattr(final_report, "weakest_dimension"):
                weakest = getattr(final_report, "weakest_dimension", None)

            yield {
                "brief_id": result.get("brief_id", brief.id),
                "variation_index": variation_index,
                "status": status,
                "cycle": cycles_used,
                "score": final_score,
                "weakest_dimension": weakest,
                "message": f"{brief.id} v{variation_index}: {status} (cycle {cycles_used})",
            }

            if status == "published":
                total_published += 1
                if final_score is not None:
                    scores_for_avg.append(final_score)
                if final_ad is not None:
                    cycle_scores = {}
                    if final_report:
                        for dim in ["clarity", "value_proposition", "call_to_action", "brand_voice", "emotional_resonance"]:
                            ds = getattr(final_report, dim, None)
                            if ds and hasattr(ds, "score"):
                                cycle_scores[dim] = ds.score
                        cycle_scores["average_score"] = getattr(final_report, "average_score", final_score)
                    else:
                        cycle_scores["average_score"] = final_score or 0
                    ads_library.append({
                        "brief_id": result.get("brief_id", brief.id),
                        "variation_index": variation_index,
                        "cycle": cycles_used,
                        "ad": final_ad.model_dump(),
                        "scores": cycle_scores,
                        "model_used": model_used,
                        "tokens_used": tokens_used,
                        "estimated_cost_usd": cost_usd,
                        "status": status,
                    })
            else:
                total_unresolvable += 1

            # iteration_log row: cycle_1_score, cycle_2_score, cycle_3_score from iteration_log in result
            log_entries = result.get("iteration_log") or []
            cycle_scores_list = [None, None, None]
            for entry in log_entries:
                c = entry.get("cycle", 0)
                if 1 <= c <= 3:
                    cycle_scores_list[c - 1] = entry.get("average_score")
            cycles_required = cycles_used
            final_avg = final_score if final_score is not None else (cycle_scores_list[cycles_required - 1] if cycles_required else None)
            weakest_targeted = weakest or (log_entries[-1].get("weakest_dimension") if log_entries else None)
            iteration_rows.append({
                "brief_id": result.get("brief_id", brief.id),
                "variation_index": variation_index,
                "difficulty": getattr(brief, "difficulty", "medium"),
                "hook_type": getattr(brief, "hook_type", ""),
                "cycle_1_score": cycle_scores_list[0],
                "cycle_2_score": cycle_scores_list[1],
                "cycle_3_score": cycle_scores_list[2],
                "cycles_required": cycles_required,
                "final_average_score": final_avg,
                "weakest_dimension_targeted": weakest_targeted,
                "status": status,
                "model_used": model_used,
                "tokens_used": tokens_used,
                "estimated_cost_usd": cost_usd,
            })

    # Write output files
    Path(ADS_LIBRARY_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(ADS_LIBRARY_PATH, "w") as f:
        json.dump({"ads": ads_library}, f, indent=2)

    with open(ITERATION_LOG_PATH, "w", newline="") as f:
        cols = [
            "brief_id", "variation_index", "difficulty", "hook_type",
            "cycle_1_score", "cycle_2_score", "cycle_3_score",
            "cycles_required", "final_average_score",
            "weakest_dimension_targeted", "status",
            "model_used", "tokens_used", "estimated_cost_usd",
        ]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(iteration_rows)

    avg_score = sum(scores_for_avg) / len(scores_for_avg) if scores_for_avg else 0.0

    if total_published < MIN_ADS_REQUIRED:
        try:
            from rich.console import Console
            Console().print(
                f"[yellow]Warning: Only {total_published} ads published. Target is {MIN_ADS_REQUIRED}.[/yellow]"
            )
        except Exception:
            pass

    yield {
        "status": "complete",
        "total_briefs": len(briefs),
        "total_variations": len(briefs) * VARIATIONS_PER_BRIEF,
        "total_published": total_published,
        "total_unresolvable": total_unresolvable,
        "avg_score": round(avg_score, 2),
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 6),
    }


def load_briefs(path: str = "data/briefs.json") -> list[AdBrief]:
    """Load and validate briefs from JSON. Skips _meta."""
    with open(path) as f:
        data = json.load(f)
    raw = data.get("briefs", data) if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    return [AdBrief.model_validate(b) for b in raw if isinstance(b, dict) and "id" in b]


def load_json(path: str) -> dict:
    """Load a JSON file. Returns {} on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


if __name__ == "__main__":
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table

    console = Console()
    briefs = load_briefs()
    competitive_context = load_json("data/competitive_context.json")
    brand_guidelines = load_json("data/brand_guidelines.json")

    if not briefs:
        console.print("[red]No briefs loaded. Check data/briefs.json.[/red]")
        raise SystemExit(1)

    table = Table(title="Pipeline progress")
    table.add_column("Brief", style="cyan")
    table.add_column("Variation", justify="right")
    table.add_column("Status", style="green")
    table.add_column("Message")

    gen = run_pipeline_streaming(briefs, competitive_context, brand_guidelines)
    final = None
    for update in gen:
        if update.get("status") == "complete":
            final = update
            break
        if "brief_id" in update:
            table.add_row(
                update.get("brief_id", ""),
                str(update.get("variation_index", "")),
                update.get("status", ""),
                update.get("message", ""),
            )
            console.print(f"[dim]{update.get('message', '')}[/dim]")

    if final:
        console.print(f"\n[green]Complete.[/green] Published: {final.get('total_published')}, Unresolvable: {final.get('total_unresolvable')}")
        console.print(f"Avg score: {final.get('avg_score')}, Tokens: {final.get('total_tokens')}, Cost: ${final.get('estimated_cost_usd', 0):.6f}")
