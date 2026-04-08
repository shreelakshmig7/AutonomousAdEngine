"""
main.py
-------
Shreelakshmi Ad Engine — Gauntlet — Pipeline entrypoint (PR4 + PR5)
-----------------------------------------------------------------------
run_pipeline_streaming() is a generator that yields progress for each
brief+variation; writes ads_library.json, iteration_log.csv (one row per
evaluation event), and quality_trends.png. Publish path triggers image gen.
Uses rich for CLI. Does not crash if published < MIN_ADS_REQUIRED.

Structured error handling:
  load_briefs_result() — load/validate briefs, returns {success, data, error}
  run_cli_pipeline()     — run pipeline once without Rich table; same shape
  __main__               — uses load_briefs_result + try/except; sys.exit only
"""

from __future__ import annotations

import csv
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from constants import VARIATION_RUN_TIMEOUT_SECONDS
from evaluate.rubrics import (
    QUALITY_THRESHOLD,
    MAX_CYCLES,
    AdBrief,
    EvaluationReport,
)
from generate.prompts import DEFAULT_SEED
from iterate.controller import run_brief

# -----------------------------------------------------------------------------
# Constants (PR4 briefing — do not import MIN_ADS_REQUIRED from rubrics)
# -----------------------------------------------------------------------------
MIN_ADS_REQUIRED: int = 50
VARIATIONS_PER_BRIEF: int = int(os.environ.get("VARIATIONS_PER_BRIEF", 5))
ADS_LIBRARY_PATH: str = "output/ads_library.json"
ITERATION_LOG_PATH: str = "output/iteration_log.csv"
QUALITY_TRENDS_PATH: str = "output/quality_trends.png"
RUNS_DIR: str = "output/runs"

# Cost estimation (PR4 briefing CORRECTION 8)
GEMINI_FLASH_COST_PER_1K_TOKENS: float = 0.000075
CLAUDE_SONNET_COST_PER_1K_TOKENS: float = 0.003

# Parallel execution — tuneable via env vars
PIPELINE_MAX_WORKERS: int = int(os.environ.get("PIPELINE_MAX_WORKERS", 10))
IMAGE_MAX_WORKERS: int = int(os.environ.get("IMAGE_MAX_WORKERS", 4))
IMAGE_STAGGER_DELAY: float = float(os.environ.get("IMAGE_STAGGER_DELAY", 2.0))  # seconds between submissions

# PR5 CSV columns — one row per evaluation event (includes ad copy per cycle for self-healing proof)
CSV_FIELDNAMES: list[str] = [
    "brief_id",
    "difficulty",
    "variation",
    "cycle",
    "primary_text",
    "headline",
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


def _make_fallback_result(brief: AdBrief, variation_index: int, error_msg: str) -> dict[str, Any]:
    """
    Build a stub result matching run_brief() shape for timeout/exception failures.

    Args:
        brief: The AdBrief for this variation.
        variation_index: Variation index (0..VARIATIONS_PER_BRIEF-1).
        error_msg: Error message (e.g. timeout text or str(exception)).

    Returns:
        dict: Full result shape so per-result processing and CSV logging work unchanged.
    """
    return {
        "brief_id": brief.id,
        "variation_index": variation_index,
        "status": "unresolvable",
        "error": error_msg,
        "cycles_used": 0,
        "final_ad": None,
        "final_score": None,
        "final_report": None,
        "changes_made": [],
        "model_used": None,
        "tokens_used": 0,
        "estimated_cost_usd": 0.0,
        "iteration_log": [
            {
                "cycle": 0,
                "status": f"unresolvable: {error_msg}",
                "error": error_msg,
                "brief_id": brief.id,
                "variation": variation_index,
                "primary_text": None,
                "headline": None,
                "cta_button": None,
                "description": None,
                "average_score": None,
                "clarity": None,
                "value_proposition": None,
                "call_to_action": None,
                "brand_voice": None,
                "emotional_resonance": None,
                "weakest_dimension": None,
                "tokens_used": 0,
                "cost_usd": 0.0,
            }
        ],
    }


def run_pipeline_streaming(
    briefs: list[AdBrief],
    competitive_context: dict,
    brand_guidelines: dict,
    output_base_dir: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Run the full pipeline for all briefs and variations; yield progress updates.

    Submits all brief×variation jobs into a single bounded ThreadPoolExecutor
    (PIPELINE_MAX_WORKERS) so multiple briefs run concurrently. Rate-limiting
    is handled at the API call level via semaphores in rate_limiter.py.

    Image generation is decoupled: published ads are collected first, then
    images are generated in a parallel post-processing pass (IMAGE_MAX_WORKERS).

    Args:
        briefs: List of validated AdBriefs.
        competitive_context: Loaded competitive_context.json.
        brand_guidelines: Loaded brand_guidelines.json.
        output_base_dir: Optional dir for this run (e.g. tmpdir in tests).
            When None, creates output/runs/<timestamp>/ and writes "latest" to output/.

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

    # Per-run output: timestamped folder or injected base dir (tests)
    if output_base_dir is not None:
        run_dir = Path(output_base_dir)
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = Path(RUNS_DIR) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    run_ads_path = run_dir / "ads_library.json"
    run_log_path = run_dir / "iteration_log.csv"
    run_trends_path = run_dir / "quality_trends.png"

    # Image generation disabled while debugging pipeline quality.
    # Re-enable by uncommenting the block below.
    image_generator = None
    # try:
    #     from images.image_generator import AdImageGenerator
    #     image_generator = AdImageGenerator(output_dir=str(images_dir))
    # except Exception:
    #     pass

    # Build brief lookup for resolving brief from (brief_id, variation_index)
    brief_by_id: dict[str, AdBrief] = {b.id: b for b in briefs}

    # Build all jobs: (brief, variation_index) pairs
    all_jobs: list[tuple[AdBrief, int]] = [
        (brief, i) for brief in briefs for i in range(VARIATIONS_PER_BRIEF)
    ]

    # Yield initial "drafting" status for all variations
    for brief, variation_index in all_jobs:
        yield {
            "brief_id": brief.id,
            "variation_index": variation_index,
            "status": "drafting",
            "cycle": 0,
            "score": None,
            "weakest_dimension": None,
            "message": f"Drafting {brief.id} variation {variation_index}",
        }

    # Phase 1: Run all variations in a bounded global thread pool
    # Semaphores in rate_limiter.py gate actual API calls, so we can safely
    # submit all jobs without overwhelming Gemini or Anthropic endpoints.
    pending_images: list[dict[str, Any]] = []  # Collected for phase 2

    with ThreadPoolExecutor(max_workers=PIPELINE_MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                run_brief,
                brief,
                competitive_context,
                brand_guidelines,
                variation_index=variation_index,
                seed=DEFAULT_SEED + variation_index,
                total_variations=VARIATIONS_PER_BRIEF,
            ): (brief, variation_index)
            for brief, variation_index in all_jobs
        }

        for future in as_completed(futures):
            brief, variation_index = futures[future]
            try:
                result = future.result(timeout=VARIATION_RUN_TIMEOUT_SECONDS)
            except TimeoutError:
                result = _make_fallback_result(
                    brief,
                    variation_index,
                    f"timeout after {VARIATION_RUN_TIMEOUT_SECONDS}s",
                )
            except Exception as e:
                result = _make_fallback_result(brief, variation_index, str(e))

            # --- Process result (same logic as before) ---
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
                "message": f"{brief.id} v{variation_index}: {status} (cycle {cycles_used})" + (f" — {result.get('error')}" if status != "published" and result.get("error") else ""),
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
                    "primary_text": entry.get("primary_text"),
                    "headline": entry.get("headline"),
                    "cta_button": entry.get("cta_button"),
                    "description": entry.get("description"),
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
                    # Published path: controller guarantees final_report is EvaluationReport.
                    if not isinstance(final_report, EvaluationReport):
                        cycle_scores = {
                            "average_score": final_score or 0,
                            "error": "final_report was not an EvaluationReport; re-run pipeline",
                        }
                    else:
                        r = final_report
                        cycle_scores = {
                            "clarity": {
                                "score": r.clarity.score,
                                "rationale": r.clarity.rationale,
                            },
                            "value_proposition": {
                                "score": r.value_proposition.score,
                                "rationale": r.value_proposition.rationale,
                            },
                            "call_to_action": {
                                "score": r.call_to_action.score,
                                "rationale": r.call_to_action.rationale,
                            },
                            "brand_voice": {
                                "score": r.brand_voice.score,
                                "rationale": r.brand_voice.rationale,
                            },
                            "emotional_resonance": {
                                "score": r.emotional_resonance.score,
                                "rationale": r.emotional_resonance.rationale,
                            },
                            "average_score": r.average_score,
                            "passes_threshold": r.passes_threshold,
                            "weakest_dimension": r.weakest_dimension,
                            "confidence": r.confidence,
                        }

                    ad_id = f"{result.get('brief_id', brief.id)}_v{variation_index}"

                    ad_entry: dict[str, Any] = {
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
                    changes_made = result.get("changes_made")
                    if changes_made:
                        ad_entry["changes_made"] = changes_made

                    # Collect image gen work for phase 2 instead of blocking here
                    if image_generator is not None and getattr(final_ad, "image_prompt", None):
                        copy_line = (
                            f'\n\nExact copy to display in this ad image (use verbatim): '
                            f'Headline: "{final_ad.headline}". CTA: {final_ad.cta_button}.'
                        )
                        tone_goal_line = (
                            f'\n\nGuardrails: Tone must be {brief.tone}; goal is {brief.goal}. '
                            'Keep all text in the image empowering and approachable, not arrogant. Use the headline and CTA verbatim above.'
                        )
                        image_prompt_with_copy = (final_ad.image_prompt or "").strip() + copy_line + tone_goal_line
                        pending_images.append({
                            "ad_id": ad_id,
                            "image_prompt": image_prompt_with_copy,
                            "ad_entry": ad_entry,
                        })
                    ads_library.append(ad_entry)
            else:
                total_unresolvable += 1
                if not log_entries and cycles_used > 0:
                    iteration_rows.append({
                        "brief_id": result.get("brief_id", brief.id),
                        "difficulty": difficulty,
                        "variation": variation_index,
                        "cycle": cycles_used,
                        "primary_text": None,
                        "headline": None,
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

    # Phase 2: Generate images in parallel for all published ads
    if pending_images and image_generator is not None:
        total_images = len(pending_images)
        images_done = 0
        yield {
            "status": "generating_images",
            "message": f"Generating {total_images} companion images…",
            "images_total": total_images,
            "images_done": 0,
        }
        with ThreadPoolExecutor(max_workers=IMAGE_MAX_WORKERS) as img_executor:
            img_futures = {}
            for img_idx, item in enumerate(pending_images):
                img_futures[
                    img_executor.submit(
                        image_generator.generate_image,
                        item["image_prompt"],
                        item["ad_id"],
                    )
                ] = item
                # Stagger submissions to avoid burst rate-limit hits
                if img_idx < len(pending_images) - 1 and IMAGE_STAGGER_DELAY > 0:
                    time.sleep(IMAGE_STAGGER_DELAY)
            for future in as_completed(img_futures):
                item = img_futures[future]
                images_done += 1
                try:
                    img_result = future.result()
                    if img_result.get("success") and img_result.get("data"):
                        # Patch image_url into the ad_entry already in ads_library
                        item["ad_entry"]["image_url"] = img_result["data"]
                        yield {
                            "status": "image_done",
                            "message": f"Image {images_done}/{total_images}: {item['ad_id']} ✓",
                            "images_total": total_images,
                            "images_done": images_done,
                            "ad_id": item["ad_id"],
                            "image_success": True,
                        }
                    else:
                        yield {
                            "status": "image_done",
                            "message": f"Image {images_done}/{total_images}: {item['ad_id']} (failed)",
                            "images_total": total_images,
                            "images_done": images_done,
                            "ad_id": item["ad_id"],
                            "image_success": False,
                        }
                except Exception:
                    yield {
                        "status": "image_done",
                        "message": f"Image {images_done}/{total_images}: {item['ad_id']} (error)",
                        "images_total": total_images,
                        "images_done": images_done,
                        "ad_id": item["ad_id"],
                        "image_success": False,
                    }

    # Write output files to run directory
    with open(run_ads_path, "w") as f:
        json.dump({"ads": ads_library}, f, indent=2)

    with open(run_log_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(iteration_rows)

    _write_quality_trends_png(cycle_to_scores, str(run_trends_path))

    # When not using injected base dir (e.g. tests), also update "latest" in output/
    if output_base_dir is None:
        Path(ADS_LIBRARY_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(run_ads_path) as src:
            data = json.load(src)
        with open(ADS_LIBRARY_PATH, "w") as f:
            json.dump(data, f, indent=2)
        with open(run_log_path) as src:
            log_content = src.read()
        with open(ITERATION_LOG_PATH, "w", newline="") as f:
            f.write(log_content)
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
    """
    Load and validate briefs from JSON. Skips _meta.

    Returns:
        List of AdBrief on success; empty list if file missing or invalid
        (legacy callers). Prefer load_briefs_result() for structured errors.
    """
    result = load_briefs_result(path)
    if result.get("success") and isinstance(result.get("data"), list):
        return result["data"]
    return []


def load_briefs_result(path: str = "data/briefs.json") -> dict[str, Any]:
    """
    Load and validate briefs from JSON; structured result only.

    Args:
        path: Path to briefs JSON.

    Returns:
        {"success": bool, "data": list[AdBrief] | None, "error": str | None}
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {
            "success": False,
            "data": None,
            "error": f"Briefs file not found: {path}",
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "success": False,
            "data": None,
            "error": f"Failed to read briefs: {e}",
        }
    try:
        raw = data.get("briefs", data) if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return {
                "success": False,
                "data": None,
                "error": "briefs JSON must contain a list",
            }
        briefs = [
            AdBrief.model_validate(b)
            for b in raw
            if isinstance(b, dict) and "id" in b
        ]
        if not briefs:
            return {
                "success": False,
                "data": None,
                "error": "No valid briefs with id in file",
            }
        return {"success": True, "data": briefs, "error": None}
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": f"Brief validation failed: {e}",
        }


def run_cli_pipeline(
    briefs_path: str = "data/briefs.json",
    competitive_context_path: str = "data/competitive_context.json",
    brand_guidelines_path: str = "data/brand_guidelines.json",
) -> dict[str, Any]:
    """
    Run the full pipeline once; structured result only (no raise to caller).

    Args:
        briefs_path: Path to briefs JSON.
        competitive_context_path: Path to competitive context JSON.
        brand_guidelines_path: Path to brand guidelines JSON.

    Returns:
        {"success": bool, "data": dict | None, "error": str | None}
        data on success is the final complete yield dict from the generator.
    """
    briefs_result = load_briefs_result(briefs_path)
    if not briefs_result.get("success"):
        return {
            "success": False,
            "data": None,
            "error": briefs_result.get("error") or "Failed to load briefs",
        }
    briefs = briefs_result["data"]
    competitive_context = load_json(competitive_context_path)
    brand_guidelines = load_json(brand_guidelines_path)

    final: dict[str, Any] | None = None
    try:
        gen = run_pipeline_streaming(briefs, competitive_context, brand_guidelines)
        for update in gen:
            if update.get("status") == "complete":
                final = update
                break
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": f"Pipeline failed: {e}",
        }

    if final is None:
        return {
            "success": False,
            "data": None,
            "error": "Pipeline did not complete (no final status)",
        }
    return {"success": True, "data": final, "error": None}


def load_json(path: str) -> dict:
    """Load a JSON file. Returns {} on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


if __name__ == "__main__":
    import sys

    from rich.console import Console
    from rich.table import Table

    console = Console()

    briefs_result = load_briefs_result()
    if not briefs_result.get("success"):
        console.print(f"[red]{briefs_result.get('error', 'No briefs loaded')}[/red]")
        sys.exit(1)

    briefs = briefs_result["data"]
    competitive_context = load_json("data/competitive_context.json")
    brand_guidelines = load_json("data/brand_guidelines.json")

    total_variations = len(briefs) * VARIATIONS_PER_BRIEF
    print(f"Pipeline starting: {len(briefs)} briefs, {total_variations} variations total.", flush=True)

    table = Table(title="Pipeline progress")
    table.add_column("Brief", style="cyan")
    table.add_column("Variation", justify="right")
    table.add_column("Status", style="green")
    table.add_column("Message")

    final = None
    try:
        gen = run_pipeline_streaming(briefs, competitive_context, brand_guidelines)
        for update in gen:
            if update.get("status") == "complete":
                final = update
                break
            if update.get("status") == "generating_images":
                console.print(f"\n[cyan]{update.get('message', 'Generating images…')}[/cyan]")
            elif update.get("status") == "image_done":
                console.print(f"[dim]{update.get('message', '')}[/dim]")
            elif "brief_id" in update:
                table.add_row(
                    update.get("brief_id", ""),
                    str(update.get("variation_index", "")),
                    update.get("status", ""),
                    update.get("message", ""),
                )
                console.print(f"[dim]{update.get('message', '')}[/dim]")
    except Exception as e:
        console.print(f"[red]Pipeline failed: {e}[/red]")
        sys.exit(1)

    if not final:
        console.print("[red]Pipeline did not complete.[/red]")
        sys.exit(1)

    console.print(
        f"\n[green]Complete.[/green] Published: {final.get('total_published')}, "
        f"Unresolvable: {final.get('total_unresolvable')}"
    )
    console.print(
        f"Avg score: {final.get('avg_score')}, Tokens: {final.get('total_tokens')}, "
        f"Cost: ${final.get('estimated_cost_usd', 0):.6f}"
    )
    sys.exit(0)
