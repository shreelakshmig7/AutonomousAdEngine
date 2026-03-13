"""
test_integration.py
-------------------
Varsity Ad Engine — Nerdy / Gauntlet — Pipeline integration tests (PR4)
-----------------------------------------------------------------------
TDD: 2 tests for run_pipeline_streaming(), output files, and progress yields.
Mocks run_brief so tests run fully offline.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from evaluate.rubrics import AdBrief, AdCopy, QUALITY_THRESHOLD


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def two_briefs() -> list[AdBrief]:
    """Two briefs for 2×2 variation runs."""
    return [
        AdBrief(
            id="brief_001",
            audience="Parents of 11th graders in the Southeast with household income $75K-$150K",
            product="SAT 1-on-1 tutoring with free diagnostic assessment",
            goal="conversion",
            tone="empathetic and urgent",
            hook_type="fear",
            difficulty="medium",
        ),
        AdBrief(
            id="brief_002",
            audience="Parents in the Northeast with household income $150K+",
            product="SAT prep with top 5% vetted tutors and 3.4M learner ratings",
            goal="conversion",
            tone="confident and results-focused",
            hook_type="stat",
            difficulty="medium",
        ),
    ]


@pytest.fixture
def mock_run_brief_published():
    """Canned run_brief return for a single published ad."""
    ad = AdCopy(
        primary_text=(
            "Is your child's SAT score standing between them and their dream school? "
            "Students improve 200+ points with a top 5% matched tutor. Start free."
        ),
        headline="Raise Your SAT Score 200 Points",
        description="Matched with a top 5% tutor in 24 hours.",
        cta_button="Start Free Assessment",
        image_prompt="Parent and teen at kitchen table, warm natural lighting, UGC style.",
    )
    return {
        "brief_id": "brief_001",
        "variation_index": 0,
        "status": "published",
        "cycles_used": 1,
        "final_ad": ad,
        "final_score": 8.0,
        "final_report": None,
        "iteration_log": [],
        "changes_made": [],
        "model_used": "gemini-2.5-flash",
        "tokens_used": 500,
        "estimated_cost_usd": 0.001,
        "error": None,
    }


SAMPLE_CONTEXT: dict = {"key_differentiators": ["200+ point improvement"]}
SAMPLE_GUIDELINES: dict = {
    "voice": {"forbidden_words_and_phrases": ["world-class", "sign up today"]},
}


# -----------------------------------------------------------------------------
# Test 1 — Pipeline generates output files
# -----------------------------------------------------------------------------
def test_main_pipeline_generates_outputs(
    two_briefs: list[AdBrief],
    mock_run_brief_published: dict,
) -> None:
    """Run run_pipeline_streaming with mocked run_brief (4 runs, all pass). Assert files and schema."""
    from main import run_pipeline_streaming

    # Build 4 results (2 briefs × 2 variations)
    def make_result(brief_id: str, variation_index: int) -> dict:
        r = dict(mock_run_brief_published)
        r["brief_id"] = brief_id
        r["variation_index"] = variation_index
        r["final_score"] = 8.0
        return r

    results = [
        make_result("brief_001", 0),
        make_result("brief_001", 1),
        make_result("brief_002", 0),
        make_result("brief_002", 1),
    ]
    result_iter = iter(results)

    def fake_generate_image(self, prompt: str, ad_id: str) -> dict:
        """Stub — no file write; return stable path for assert."""
        return {"success": True, "data": f"output/images/{ad_id}.png", "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        ads_path = Path(tmpdir) / "ads_library.json"
        log_path = Path(tmpdir) / "iteration_log.csv"
        with (
            patch("main.VARIATIONS_PER_BRIEF", 2),
            patch("main.run_brief", side_effect=lambda *a, **k: next(result_iter)),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                two_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES, output_base_dir=str(tmpdir)
            )
            for _ in gen:
                pass

        assert ads_path.exists(), "ads_library.json should exist"
        with open(ads_path) as f:
            ads_data = json.load(f)
        ads_list = ads_data.get("ads", ads_data) if isinstance(ads_data, dict) else ads_data
        if not isinstance(ads_list, list):
            ads_list = [ads_data]
        assert len(ads_list) == 4, f"Expected 4 entries, got {len(ads_list)}"

        required_keys = {"brief_id", "variation_index", "cycle", "ad", "scores", "model_used", "tokens_used", "status"}
        for entry in ads_list:
            for key in required_keys:
                assert key in entry, f"Missing key {key} in entry"
            # PR5 — image_url present when generator succeeds (mocked)
            assert entry.get("image_url"), "image_url must be set for published ads when image gen succeeds"
            scores = entry.get("scores", {})
            avg = scores.get("average_score", entry.get("final_score", 0))
            assert avg >= QUALITY_THRESHOLD, f"Entry score {avg} below threshold"

        assert log_path.exists(), "iteration_log.csv should exist"
        log_content = log_path.read_text()
        # PR5 — one row per evaluation event; header must list all columns
        required_cols = [
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
        for col in required_cols:
            assert col in log_content, f"Missing column {col} in iteration_log.csv"


# -----------------------------------------------------------------------------
# Test 2 — Pipeline yields progress updates
# -----------------------------------------------------------------------------
def test_pipeline_yields_progress_updates(
    two_briefs: list[AdBrief],
    mock_run_brief_published: dict,
) -> None:
    """Collect all yielded dicts. Assert non-final have brief_id, status, cycle, message; final has status=complete."""
    from main import run_pipeline_streaming

    results = [dict(mock_run_brief_published, brief_id=b.id, variation_index=i) for b in two_briefs for i in range(2)]

    def fake_generate_image(self, prompt: str, ad_id: str) -> dict:
        return {"success": True, "data": f"output/images/{ad_id}.png", "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.VARIATIONS_PER_BRIEF", 2),
            patch("main.run_brief", side_effect=results),
            patch(
                "images.image_generator.AdImageGenerator.generate_image",
                fake_generate_image,
            ),
        ):
            gen = run_pipeline_streaming(
                two_briefs, SAMPLE_CONTEXT, SAMPLE_GUIDELINES, output_base_dir=str(tmpdir)
            )
            yielded = list(gen)

    assert len(yielded) >= 1, "Generator must yield at least one update"
    final = yielded[-1]
    assert final.get("status") == "complete", f"Final yield must have status=complete, got {final.get('status')}"
    assert "total_published" in final
    assert "total_unresolvable" in final
    assert "avg_score" in final
    assert "total_tokens" in final
    assert "estimated_cost_usd" in final

    for msg in yielded[:-1]:
        assert "brief_id" in msg or "status" in msg
        assert "status" in msg
        assert "message" in msg
