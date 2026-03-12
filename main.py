"""
main.py
-------
Varsity Ad Engine — Nerdy / Gauntlet — Pipeline entrypoint (PR4 + PR5)
-----------------------------------------------------------------------
run_pipeline_streaming() is a generator that yields progress for each
brief+variation; writes ads_library.json, iteration_log.csv (one row per
evaluation event), and quality_trends.png. Publish path triggers image gen.
Uses rich for CLI. Does not crash if published < MIN_ADS_REQUIRED.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
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
QUALITY_TRENDS_PATH: str = "output/quality_trends.png"

# Cost estimation (PR4 briefing CORRECTION 8)
GEMINI_FLASH_COST_PER_1K_TOKENS: float = 0.000075
CLAUDE_SONNET_COST_PER_1K_TOKENS: float = 0.003

# PR5 CSV columns — one row per evaluation event
CSV_FIELDNAMES: list[str] = [
    "brief_id",
    "difficulty",
    "variation",
    "cycle",
    "clarity",
    "value_prop",
    "cta",
    "brand_voice",
    "emotional_resonance",
    "average_score",
    "weakest_dimension",
    "status",
    "tokens_used",
    "cost_usd",
]


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


def _write_quality_trends_png(
    cycle_to_scores: dict[int, list[float]],
    path: str,
) -> None:
    """
    Write matplotlib line chart: mean average_score per cycle.

    Args:
        cycle_to_scores: cycle -> list of average_score values.
        path: Output PNG path.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    cycles = sorted(cycle_to_scores.keys())
    if not cycles:
        return
    means = []
    for c in cycles:
        scores = [s for s in cycle_to_scores[c] if s is not None]
        if scores:
            means.append(sum(scores) / len(scores))
        else:
            means.append(0.0)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    plt.plot(cycles, means, marker="o", linewidth=2)
    plt.xlabel("Cycle")
    plt.ylabel("Mean average score")
    plt.title("Quality trend across iteration cycles")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()


def run_pipeline_streaming(
    briefs: list[AdBrief],
    competitive_context: dict,
    brand_guidelines: dict,
) -> Generator[dict[str, Any], None, None]:
    """
    Run the full pipeline for all briefs and variations; yield progress updates.

    For each brief × variation_index runs run_brief(). Writes ads_library.json,
    iteration_log.csv (one row per evaluation event), quality_trends.png.
    Final yield has status "complete" and aggregates.

    Args:
        briefs: List of validated AdBriefs.
        competitive_context: Loaded competitive_context.json.
        brand_guidelines: Loaded brand_guidelines.json.

    Yields:
        Progress dicts and final complete dict.
    """
    ads_library: list[dict] = []
    iteration_rows: list[dict[str, Any]] = []
    total_published = 0
    total_unresolvable = 0
    total_tokens = 0
    total_cost = 0.0
    scores_for_avg: list[float] = []
    # For quality_trends: cycle -> scores
    cycle_to_scores: dict[int, list[float]] = defaultdict(list)

    image_generator = None
    try:
        from images.image_generator import AdImageGenerator

        image_generator = AdImageGenerator()
    except Exception:
        pass

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

            difficulty = getattr(brief, "difficulty", "medium")
            log_entries = result.get("iteration_log") or []

            # One CSV row per evaluation event
            for entry in log_entries:
                c = int(entry.get("cycle") or 0)
                avg = entry.get("average_score")
                if avg is not None:
                    try:
                        cycle_to_scores[c].append(float(avg))
                    except (TypeError, ValueError):
                        pass
                row_status = entry.get("status") or "below_threshold"
                if entry.get("scan_failed"):
                    row_status = "scan_failed"
                iteration_rows.append({
                    "brief_id": result.get("brief_id", brief.id),
                    "difficulty": difficulty,
                    "variation": variation_index,
                    "cycle": c,
                    "clarity": entry.get("clarity"),
                    "value_prop": entry.get("value_proposition"),
                    "cta": entry.get("call_to_action"),
                    "brand_voice": entry.get("brand_voice"),
                    "emotional_resonance": entry.get("emotional_resonance"),
                    "average_score": avg,
                    "weakest_dimension": entry.get("weakest_dimension"),
                    "status": row_status,
                    "tokens_used": tokens_used,
                    "cost_usd": cost_usd,
                })

            if status == "published":
                total_published += 1
                if final_score is not None:
                    scores_for_avg.append(final_score)
                if final_ad is not None:
                    cycle_scores = {}
                    if final_report:
                        for dim in [
                            "clarity",
                            "value_proposition",
                            "call_to_action",
                            "brand_voice",
                            "emotional_resonance",
                        ]:
                            ds = getattr(final_report, dim, None)
                            if ds and hasattr(ds, "score"):
                                cycle_scores[dim] = ds.score
                        cycle_scores["average_score"] = getattr(
                            final_report, "average_score", final_score
                        )
                    else:
                        cycle_scores["average_score"] = final_score or 0

                    ad_id = f"{result.get('brief_id', brief.id)}_v{variation_index}"
                    image_url = None
                    if image_generator is not None and getattr(final_ad, "image_prompt", None):
                        img_result = image_generator.generate_image(
                            final_ad.image_prompt, ad_id
                        )
                        if img_result.get("success") and img_result.get("data"):
                            image_url = img_result["data"]

                    entry = {
                        "brief_id": result.get("brief_id", brief.id),
                        "variation_index": variation_index,
                        "cycle": cycles_used,
                        "ad": final_ad.model_dump(),
                        "scores": cycle_scores,
                        "model_used": model_used,
                        "tokens_used": tokens_used,
                        "estimated_cost_usd": cost_usd,
                        "status": status,
                    }
                    if image_url:
                        entry["image_url"] = image_url
                    ads_library.append(entry)
            else:
                total_unresolvable += 1
                # Unresolvable with no log entries still need a summary row if cycles ran
                if not log_entries and cycles_used > 0:
                    iteration_rows.append({
                        "brief_id": result.get("brief_id", brief.id),
                        "difficulty": difficulty,
                        "variation": variation_index,
                        "cycle": cycles_used,
                        "clarity": None,
                        "value_prop": None,
                        "cta": None,
                        "brand_voice": None,
                        "emotional_resonance": None,
                        "average_score": final_score,
                        "weakest_dimension": weakest,
                        "status": status,
                        "tokens_used": tokens_used,
                        "cost_usd": cost_usd,
                    })

    # Write output files
    Path(ADS_LIBRARY_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(ADS_LIBRARY_PATH, "w") as f:
        json.dump({"ads": ads_library}, f, indent=2)

    with open(ITERATION_LOG_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(iteration_rows)

    _write_quality_trends_png(cycle_to_scores, QUALITY_TRENDS_PATH)

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
