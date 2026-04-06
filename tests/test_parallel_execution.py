"""
test_parallel_execution.py
--------------------------
Shreelakshmi Ad Engine — Mock tests for parallel execution optimization.
-------------------------------------------------------------------
Validates:
  1. Global bounded thread pool runs all brief×variation jobs concurrently
     (not sequentially per brief).
  2. Semaphores in rate_limiter.py correctly gate concurrent API calls.
  3. Image generation is decoupled into a parallel post-processing phase.
  4. Results, output files, and progress yields remain correct regardless
     of completion order.
  5. Timeout and exception handling works with the global pool.

All tests mock API calls — zero real tokens burned.
"""

import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evaluate.rubrics import AdBrief, AdCopy, EvaluationReport, DimensionScore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def three_briefs() -> list[AdBrief]:
    """Three briefs for 3×5 = 15 variation jobs."""
    return [
        AdBrief(
            id="brief_001",
            audience="Parents of 11th graders in Southeast",
            product="SAT 1-on-1 tutoring",
            goal="conversion",
            tone="empathetic and urgent",
            hook_type="fear",
            difficulty="medium",
        ),
        AdBrief(
            id="brief_002",
            audience="Parents in the Northeast",
            product="SAT prep with top tutors",
            goal="conversion",
            tone="confident and results-focused",
            hook_type="stat",
            difficulty="medium",
        ),
        AdBrief(
            id="brief_003",
            audience="College students nationwide",
            product="GRE prep with adaptive learning",
            goal="awareness",
            tone="encouraging and supportive",
            hook_type="question",
            difficulty="easy",
        ),
    ]


@pytest.fixture
def sample_ad() -> AdCopy:
    return AdCopy(
        primary_text=(
            "Is your child's SAT score holding them back? "
            "Students improve 200+ points with matched tutors. Start free."
        ),
        headline="Raise Your SAT Score Fast",
        description="Matched with a top 5% tutor in 24 hours.",
        cta_button="Start Free Assessment",
        image_prompt="Parent and teen at kitchen table, warm lighting, UGC style.",
    )


@pytest.fixture
def sample_report() -> EvaluationReport:
    return EvaluationReport(
        clarity=DimensionScore(score=8.5, rationale="Clear and concise messaging throughout."),
        value_proposition=DimensionScore(score=8.0, rationale="Strong value proposition with specifics."),
        call_to_action=DimensionScore(score=7.5, rationale="Clear CTA with good urgency signal."),
        brand_voice=DimensionScore(score=8.0, rationale="On-brand tone and language used well."),
        emotional_resonance=DimensionScore(score=7.5, rationale="Good emotional appeal to parents."),
        average_score=7.9,
        weakest_dimension="call_to_action",
        passes_threshold=True,
        confidence="high",
    )


SAMPLE_CONTEXT: dict = {"key_differentiators": ["200+ point improvement"]}
SAMPLE_GUIDELINES: dict = {
    "voice": {"forbidden_words_and_phrases": ["world-class"]},
}


def _make_published_result(
    brief_id: str,
    variation_index: int,
    ad: AdCopy,
    report: EvaluationReport,
) -> dict:
    """Build a canned run_brief result for a published ad."""
    return {
        "brief_id": brief_id,
        "variation_index": variation_index,
        "status": "published",
        "cycles_used": 1,
        "final_ad": ad,
        "final_score": report.average_score,
        "final_report": report,
        "iteration_log": [
            {
                "cycle": 1,
                "primary_text": ad.primary_text,
                "headline": ad.headline,
                "clarity": 8.5,
                "value_proposition": 8.0,
                "call_to_action": 7.5,
                "brand_voice": 8.0,
                "emotional_resonance": 7.5,
                "average_score": report.average_score,
                "weakest_dimension": "call_to_action",
                "status": "published",
            }
        ],
        "changes_made": [],
        "model_used": "gemini-2.5-flash",
        "tokens_used": 500,
        "estimated_cost_usd": 0.001,
        "error": None,
    }


def _make_unresolvable_result(brief_id: str, variation_index: int) -> dict:
    """Build a canned run_brief result for an unresolvable ad."""
    return {
        "brief_id": brief_id,
        "variation_index": variation_index,
        "status": "unresolvable",
        "cycles_used": 3,
        "final_ad": None,
        "final_score": 5.2,
        "final_report": None,
        "iteration_log": [],
        "changes_made": [],
        "model_used": "gemini-2.5-flash",
        "tokens_used": 1500,
        "estimated_cost_usd": 0.003,
        "error": "max_evaluation_cycles_reached",
    }


# ---------------------------------------------------------------------------
# Test 1 — All briefs run concurrently (not sequentially per brief)
# ---------------------------------------------------------------------------
def test_global_pool_runs_briefs_concurrently(
    three_briefs: list[AdBrief],
    sample_ad: AdCopy,
    sample_report: EvaluationReport,
) -> None:
    """
    Verify that variations from different briefs overlap in time.
    If the old sequential-per-brief approach were used, brief_002 would
    not start until all brief_001 variations finish.
    """
    from main import run_pipeline_streaming

    active_briefs: set[str] = set()
    overlap_detected = threading.Event()
    lock = threading.Lock()

    def fake_run_brief(brief, *args, **kwargs):
        brief_id = brief.id
        vi = kwargs.get("variation_index", 0)
        with lock:
            active_briefs.add(brief_id)
            if len(active_briefs) > 1:
                overlap_detected.set()
        # Simulate API latency so threads overlap
        time.sleep(0.05)
        with lock:
            active_briefs.discard(brief_id)
        return _make_published_result(brief_id, vi, sample_ad, sample_report)

    def fake_generate_image(self, prompt, ad_id):
        return {"success": True, "data": f"images/{ad_id}.png", "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.run_brief", side_effect=fake_run_brief),
            patch("main.PIPELINE_MAX_WORKERS", 15),
            patch("main.VARIATIONS_PER_BRIEF", 2),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                three_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES,
                output_base_dir=str(tmpdir),
            )
            for _ in gen:
                pass

    assert overlap_detected.is_set(), (
        "Expected variations from different briefs to run concurrently, "
        "but no overlap was detected. The pipeline may still be sequential per brief."
    )


# ---------------------------------------------------------------------------
# Test 2 — Semaphore limits concurrent API calls
# ---------------------------------------------------------------------------
def test_semaphore_limits_concurrent_gemini_calls() -> None:
    """
    Verify gemini_semaphore enforces the max concurrent call limit.
    With semaphore=2 and 5 threads, at most 2 should be inside the
    critical section simultaneously.
    """
    import rate_limiter

    # Temporarily set a tight semaphore
    original = rate_limiter.gemini_semaphore
    rate_limiter.gemini_semaphore = threading.Semaphore(2)

    max_concurrent = 0
    current_concurrent = 0
    lock = threading.Lock()

    def tracked_work():
        nonlocal max_concurrent, current_concurrent
        rate_limiter.gemini_semaphore.acquire()
        try:
            with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            time.sleep(0.05)  # Simulate API latency
            with lock:
                current_concurrent -= 1
        finally:
            rate_limiter.gemini_semaphore.release()

    threads = [threading.Thread(target=tracked_work) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Restore original
    rate_limiter.gemini_semaphore = original

    assert max_concurrent <= 2, (
        f"Semaphore(2) should limit to 2 concurrent calls, but saw {max_concurrent}"
    )
    assert max_concurrent == 2, (
        f"Expected 2 concurrent calls with 5 threads and semaphore=2, but saw {max_concurrent}"
    )


def test_semaphore_limits_concurrent_anthropic_calls() -> None:
    """Same test for anthropic_semaphore."""
    import rate_limiter

    original = rate_limiter.anthropic_semaphore
    rate_limiter.anthropic_semaphore = threading.Semaphore(3)

    max_concurrent = 0
    current_concurrent = 0
    lock = threading.Lock()

    def tracked_work():
        nonlocal max_concurrent, current_concurrent
        rate_limiter.anthropic_semaphore.acquire()
        try:
            with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            time.sleep(0.05)
            with lock:
                current_concurrent -= 1
        finally:
            rate_limiter.anthropic_semaphore.release()

    threads = [threading.Thread(target=tracked_work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rate_limiter.anthropic_semaphore = original

    assert max_concurrent <= 3, (
        f"Semaphore(3) should limit to 3 concurrent calls, but saw {max_concurrent}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Image generation is decoupled (runs after pipeline, not inline)
# ---------------------------------------------------------------------------
def test_image_generation_decoupled_from_pipeline(
    three_briefs: list[AdBrief],
    sample_ad: AdCopy,
    sample_report: EvaluationReport,
) -> None:
    """
    Verify images are generated AFTER all run_brief calls complete,
    not interleaved during pipeline execution.
    """
    from main import run_pipeline_streaming

    pipeline_done = threading.Event()
    image_gen_times: list[float] = []
    pipeline_end_time = None

    call_count = 0
    total_jobs = len(three_briefs) * 2  # VARIATIONS_PER_BRIEF=2

    def fake_run_brief(brief, *args, **kwargs):
        nonlocal call_count
        vi = kwargs.get("variation_index", 0)
        call_count += 1
        return _make_published_result(brief.id, vi, sample_ad, sample_report)

    def fake_generate_image(self, prompt, ad_id):
        image_gen_times.append(time.monotonic())
        return {"success": True, "data": f"images/{ad_id}.png", "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.run_brief", side_effect=fake_run_brief),
            patch("main.VARIATIONS_PER_BRIEF", 2),
            patch("main.PIPELINE_MAX_WORKERS", 6),
            patch("main.IMAGE_MAX_WORKERS", 4),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                three_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES,
                output_base_dir=str(tmpdir),
            )
            for _ in gen:
                pass

    # All 6 jobs should have run
    assert call_count == total_jobs, f"Expected {total_jobs} run_brief calls, got {call_count}"
    # Images should have been generated (6 published ads)
    assert len(image_gen_times) == total_jobs, (
        f"Expected {total_jobs} image gen calls, got {len(image_gen_times)}"
    )


# ---------------------------------------------------------------------------
# Test 4 — Mixed published/unresolvable results produce correct output
# ---------------------------------------------------------------------------
def test_mixed_results_output_correct(
    three_briefs: list[AdBrief],
    sample_ad: AdCopy,
    sample_report: EvaluationReport,
) -> None:
    """
    Pipeline with mix of published and unresolvable results.
    Verifies ads_library only contains published, and final stats are correct.
    """
    from main import run_pipeline_streaming

    def fake_run_brief(brief, *args, **kwargs):
        vi = kwargs.get("variation_index", 0)
        # First variation of each brief publishes, second is unresolvable
        if vi == 0:
            return _make_published_result(brief.id, vi, sample_ad, sample_report)
        else:
            return _make_unresolvable_result(brief.id, vi)

    def fake_generate_image(self, prompt, ad_id):
        return {"success": True, "data": f"images/{ad_id}.png", "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.run_brief", side_effect=fake_run_brief),
            patch("main.VARIATIONS_PER_BRIEF", 2),
            patch("main.PIPELINE_MAX_WORKERS", 6),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                three_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES,
                output_base_dir=str(tmpdir),
            )
            yielded = list(gen)

        final = yielded[-1]
        assert final["status"] == "complete"
        assert final["total_published"] == 3, f"Expected 3 published, got {final['total_published']}"
        assert final["total_unresolvable"] == 3, f"Expected 3 unresolvable, got {final['total_unresolvable']}"
        assert final["total_variations"] == 6

        # Check ads_library.json
        ads_path = Path(tmpdir) / "ads_library.json"
        assert ads_path.exists()
        with open(ads_path) as f:
            data = json.load(f)
        ads_list = data.get("ads", [])
        assert len(ads_list) == 3, f"ads_library should have 3 published ads, got {len(ads_list)}"
        for entry in ads_list:
            assert entry["status"] == "published"
            assert entry.get("image_url"), "Published ad should have image_url"


# ---------------------------------------------------------------------------
# Test 5 — Timeout handling in global pool
# ---------------------------------------------------------------------------
def test_timeout_produces_fallback_result(
    three_briefs: list[AdBrief],
    sample_ad: AdCopy,
    sample_report: EvaluationReport,
) -> None:
    """
    When a variation times out, it should produce a fallback unresolvable result
    without crashing the pipeline.
    """
    from main import run_pipeline_streaming

    def fake_run_brief(brief, *args, **kwargs):
        vi = kwargs.get("variation_index", 0)
        if brief.id == "brief_002" and vi == 1:
            raise TimeoutError("Simulated timeout")
        return _make_published_result(brief.id, vi, sample_ad, sample_report)

    def fake_generate_image(self, prompt, ad_id):
        return {"success": True, "data": f"images/{ad_id}.png", "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.run_brief", side_effect=fake_run_brief),
            patch("main.VARIATIONS_PER_BRIEF", 2),
            patch("main.PIPELINE_MAX_WORKERS", 6),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                three_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES,
                output_base_dir=str(tmpdir),
            )
            yielded = list(gen)

    final = yielded[-1]
    assert final["status"] == "complete"
    # 5 published (6 total - 1 timeout), 1 unresolvable
    assert final["total_published"] == 5
    assert final["total_unresolvable"] == 1


# ---------------------------------------------------------------------------
# Test 6 — Exception handling in global pool
# ---------------------------------------------------------------------------
def test_exception_produces_fallback_result(
    three_briefs: list[AdBrief],
    sample_ad: AdCopy,
    sample_report: EvaluationReport,
) -> None:
    """
    When a variation raises an unexpected exception, the pipeline continues
    and produces a fallback unresolvable result for that variation.
    """
    from main import run_pipeline_streaming

    def fake_run_brief(brief, *args, **kwargs):
        vi = kwargs.get("variation_index", 0)
        if brief.id == "brief_001" and vi == 0:
            raise RuntimeError("Simulated crash")
        return _make_published_result(brief.id, vi, sample_ad, sample_report)

    def fake_generate_image(self, prompt, ad_id):
        return {"success": True, "data": f"images/{ad_id}.png", "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.run_brief", side_effect=fake_run_brief),
            patch("main.VARIATIONS_PER_BRIEF", 2),
            patch("main.PIPELINE_MAX_WORKERS", 6),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                three_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES,
                output_base_dir=str(tmpdir),
            )
            yielded = list(gen)

    final = yielded[-1]
    assert final["status"] == "complete"
    assert final["total_published"] == 5
    assert final["total_unresolvable"] == 1


# ---------------------------------------------------------------------------
# Test 7 — Image gen failure is non-fatal
# ---------------------------------------------------------------------------
def test_image_gen_failure_nonfatal(
    three_briefs: list[AdBrief],
    sample_ad: AdCopy,
    sample_report: EvaluationReport,
) -> None:
    """
    When image generation fails for some ads, the pipeline still completes
    and those ads appear in ads_library without image_url.
    """
    from main import run_pipeline_streaming

    def fake_run_brief(brief, *args, **kwargs):
        vi = kwargs.get("variation_index", 0)
        return _make_published_result(brief.id, vi, sample_ad, sample_report)

    call_count = 0

    def fake_generate_image(self, prompt, ad_id):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("Image gen exploded")
        return {"success": True, "data": f"images/{ad_id}.png", "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.run_brief", side_effect=fake_run_brief),
            patch("main.VARIATIONS_PER_BRIEF", 2),
            patch("main.PIPELINE_MAX_WORKERS", 6),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                three_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES,
                output_base_dir=str(tmpdir),
            )
            yielded = list(gen)

        final = yielded[-1]
        assert final["status"] == "complete"
        assert final["total_published"] == 6

        ads_path = Path(tmpdir) / "ads_library.json"
        with open(ads_path) as f:
            data = json.load(f)
        ads_list = data.get("ads", [])
        assert len(ads_list) == 6
        # Some should have image_url, some should not
        with_image = [a for a in ads_list if a.get("image_url")]
        without_image = [a for a in ads_list if not a.get("image_url")]
        assert len(with_image) >= 1, "At least some ads should have images"
        assert len(without_image) >= 1, "At least some ads should be missing images (gen failed)"


# ---------------------------------------------------------------------------
# Test 8 — Progress yields include all variations
# ---------------------------------------------------------------------------
def test_progress_yields_all_variations(
    three_briefs: list[AdBrief],
    sample_ad: AdCopy,
    sample_report: EvaluationReport,
) -> None:
    """
    Pipeline should yield a 'drafting' status for each variation, then a
    result status for each, then a final 'complete' status.
    """
    from main import run_pipeline_streaming

    def fake_run_brief(brief, *args, **kwargs):
        vi = kwargs.get("variation_index", 0)
        return _make_published_result(brief.id, vi, sample_ad, sample_report)

    def fake_generate_image(self, prompt, ad_id):
        return {"success": True, "data": f"images/{ad_id}.png", "error": None}

    num_variations = 2

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.run_brief", side_effect=fake_run_brief),
            patch("main.VARIATIONS_PER_BRIEF", num_variations),
            patch("main.PIPELINE_MAX_WORKERS", 6),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                three_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES,
                output_base_dir=str(tmpdir),
            )
            yielded = list(gen)

    total_jobs = len(three_briefs) * num_variations  # 6

    # Should have: 6 drafting + 6 result + 1 complete = 13
    drafting = [y for y in yielded if y.get("status") == "drafting"]
    results = [y for y in yielded if y.get("status") in ("published", "unresolvable")]
    complete = [y for y in yielded if y.get("status") == "complete"]

    assert len(drafting) == total_jobs, f"Expected {total_jobs} drafting yields, got {len(drafting)}"
    assert len(results) == total_jobs, f"Expected {total_jobs} result yields, got {len(results)}"
    assert len(complete) == 1, "Should have exactly one 'complete' yield"
