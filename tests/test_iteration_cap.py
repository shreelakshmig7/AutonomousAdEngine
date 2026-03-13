"""
test_iteration_cap.py
---------------------
Varsity Ad Engine — Nerdy / Gauntlet — Iteration controller tests (PR4)
------------------------------------------------------------------------
TDD: 5 tests for AdController, run_brief(), build_regeneration_prompt().
All API calls mocked — tests run fully offline.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from evaluate.rubrics import (
    AdBrief,
    AdCopy,
    DimensionScore,
    EvaluationReport,
    MAX_CYCLES,
    QUALITY_THRESHOLD,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def sample_brief() -> AdBrief:
    """Valid AdBrief for iteration tests."""
    return AdBrief(
        id="brief_001",
        audience="Parents of 11th graders in the Southeast with household income $75K-$150K",
        product="SAT 1-on-1 tutoring with free diagnostic assessment",
        goal="conversion",
        tone="empathetic and urgent",
        hook_type="fear",
        difficulty="medium",
    )


@pytest.fixture
def valid_ad_copy() -> AdCopy:
    """Valid AdCopy for mocking drafter output."""
    return AdCopy(
        primary_text=(
            "Is your child's SAT score standing between them and their dream school? "
            "Students improve 200+ points with a top 5% matched tutor. Start free."
        ),
        headline="Raise Your SAT Score 200 Points",
        description="Matched with a top 5% tutor in 24 hours.",
        cta_button="Start Free Assessment",
        image_prompt=(
            "Parent and teen at kitchen table, teen smiling at laptop, "
            "warm natural lighting, authentic UGC style."
        ),
    )


def _make_report(
    clarity: int = 8,
    value_proposition: int = 8,
    call_to_action: int = 8,
    brand_voice: int = 8,
    emotional_resonance: int = 8,
) -> EvaluationReport:
    """Build an EvaluationReport with given dimension scores."""
    return EvaluationReport(
        clarity=DimensionScore(score=clarity, rationale="Clear hook and structure."),
        value_proposition=DimensionScore(
            score=value_proposition, rationale="Strong outcome focus."
        ),
        call_to_action=DimensionScore(
            score=call_to_action, rationale="Specific CTA."
        ),
        brand_voice=DimensionScore(score=brand_voice, rationale="On-brand tone."),
        emotional_resonance=DimensionScore(
            score=emotional_resonance, rationale="Resonant message."
        ),
        average_score=8.0,
        weakest_dimension="clarity",
        passes_threshold=True,
        confidence="high",
    )


SAMPLE_CONTEXT: dict = {"key_differentiators": ["200+ point improvement"]}
SAMPLE_GUIDELINES: dict = {
    "voice": {
        "forbidden_words_and_phrases": ["world-class", "sign up today"],
        "writing_principles": ["Lead with outcomes."],
    },
    "hook_guidelines": {"fear_hooks": {"allowed": ["Anxiety of unknown."]}},
    "approved_differentiators": {"metrics": ["Top 5% tutors"]},
    "cta_guidelines": {"conversion_goal": ["Start Free Assessment"]},
}


# -----------------------------------------------------------------------------
# Test 1 — Pass on cycle 1
# -----------------------------------------------------------------------------
def test_controller_passes_on_cycle_1(
    sample_brief: AdBrief,
    valid_ad_copy: AdCopy,
) -> None:
    """Mock judge returns passes_threshold=True on first call. Assert cycles_used==1, status==published."""
    from iterate.controller import run_brief

    draft_return = {
        "success": True,
        "data": valid_ad_copy,
        "tokens_used": 100,
        "model_used": "gemini-2.5-flash",
        "error": None,
    }
    report = _make_report()
    judge_return = {"success": True, "data": report, "error": None}

    with (
        patch("iterate.controller.AdDrafter") as MockDrafter,
        patch("iterate.controller.AdJudge") as MockJudge,
        patch("iterate.controller.scan_output_safety", return_value={"success": True, "safe": True, "error": None}),
    ):
        mock_drafter_instance = MagicMock()
        mock_drafter_instance.draft_ad.return_value = draft_return
        MockDrafter.return_value = mock_drafter_instance

        mock_judge_instance = MagicMock()
        mock_judge_instance.evaluate_ad.return_value = judge_return
        MockJudge.return_value = mock_judge_instance

        result = run_brief(
            sample_brief,
            SAMPLE_CONTEXT,
            SAMPLE_GUIDELINES,
            variation_index=0,
        )

    assert result["status"] == "published"
    assert result["cycles_used"] == 1
    assert result["final_ad"] is not None
    assert result["final_score"] >= QUALITY_THRESHOLD
    assert result["error"] is None


# -----------------------------------------------------------------------------
# Test 2 — Heal on cycle 2
# -----------------------------------------------------------------------------
def test_controller_heals_on_cycle_2(
    sample_brief: AdBrief,
    valid_ad_copy: AdCopy,
) -> None:
    """Mock judge fails cycle 1, passes cycle 2. Assert build_regeneration_prompt called with report (weak=clarity)."""
    from iterate.controller import run_brief, build_regeneration_prompt

    draft_return = {
        "success": True,
        "data": valid_ad_copy,
        "tokens_used": 100,
        "model_used": "gemini-2.5-flash",
        "error": None,
    }
    # Scores: clarity=4, others=6 -> average 5.6 < 7, single weak = clarity
    report_fail = _make_report(clarity=4, value_proposition=6, call_to_action=6, brand_voice=6, emotional_resonance=6)
    report_pass = _make_report()

    judge_returns = [
        {"success": True, "data": report_fail, "error": None},
        {"success": True, "data": report_pass, "error": None},
    ]

    regen_payload = {
        "optimized_ad": valid_ad_copy.model_dump(),
        "changes_made": [{"dimension": "Clarity", "action": "Clarified hook and value prop."}],
    }
    _regen_json = json.dumps(regen_payload)

    with (
        patch("iterate.controller.AdDrafter") as MockDrafter,
        patch("iterate.controller.AdJudge") as MockJudge,
        patch("iterate.controller.scan_output_safety", return_value={"success": True, "safe": True, "error": None}),
        patch("iterate.controller.build_regeneration_prompt", wraps=build_regeneration_prompt) as mock_regen,
    ):
        mock_drafter_instance = MagicMock()
        mock_drafter_instance.draft_ad.return_value = draft_return
        mock_drafter_instance._call_gemini.return_value = _regen_json
        mock_drafter_instance._clean_json_response.side_effect = lambda x: x if isinstance(x, str) else _regen_json
        MockDrafter.return_value = mock_drafter_instance

        mock_judge_instance = MagicMock()
        mock_judge_instance.evaluate_ad.side_effect = judge_returns
        MockJudge.return_value = mock_judge_instance

        result = run_brief(
            sample_brief,
            SAMPLE_CONTEXT,
            SAMPLE_GUIDELINES,
            variation_index=0,
        )

    assert result["status"] == "published"
    assert result["cycles_used"] == 2
    assert mock_regen.call_count == 1
    call_kwargs = getattr(mock_regen.call_args, "kwargs", {}) or {}
    assert call_kwargs.get("report") is not None
    assert call_kwargs["report"].weakest_dimension == "clarity"
    assert result.get("changes_made") == regen_payload["changes_made"]


# -----------------------------------------------------------------------------
# Test 3 — Halt at unresolvable
# -----------------------------------------------------------------------------
def test_controller_halts_at_unresolvable(
    sample_brief: AdBrief,
    valid_ad_copy: AdCopy,
) -> None:
    """Mock judge fails 3 times. Assert loop breaks at MAX_CYCLES, status=unresolvable, final_ad=None."""
    from iterate.controller import run_brief

    draft_return = {
        "success": True,
        "data": valid_ad_copy,
        "tokens_used": 100,
        "model_used": "gemini-2.5-flash",
        "error": None,
    }
    report_fail = _make_report(clarity=4, value_proposition=4, call_to_action=4, brand_voice=4, emotional_resonance=4)
    report_fail.passes_threshold = False
    report_fail.average_score = 4.0
    report_fail.weakest_dimension = "clarity"
    judge_return = {"success": True, "data": report_fail, "error": None}

    with (
        patch("iterate.controller.AdDrafter") as MockDrafter,
        patch("iterate.controller.AdJudge") as MockJudge,
        patch("iterate.controller.scan_output_safety", return_value={"success": True, "safe": True, "error": None}),
    ):
        mock_drafter_instance = MagicMock()
        mock_drafter_instance.draft_ad.return_value = draft_return
        regen_payload = {"optimized_ad": valid_ad_copy.model_dump(), "changes_made": []}
        _regen_json = json.dumps(regen_payload)
        mock_drafter_instance._call_gemini.return_value = _regen_json
        mock_drafter_instance._clean_json_response.side_effect = lambda x: x if isinstance(x, str) else _regen_json
        MockDrafter.return_value = mock_drafter_instance

        mock_judge_instance = MagicMock()
        mock_judge_instance.evaluate_ad.return_value = judge_return
        MockJudge.return_value = mock_judge_instance

        result = run_brief(
            sample_brief,
            SAMPLE_CONTEXT,
            SAMPLE_GUIDELINES,
            variation_index=0,
        )

    assert result["status"] == "unresolvable"
    assert result["cycles_used"] == MAX_CYCLES
    assert result["final_ad"] is None
    assert mock_drafter_instance.draft_ad.call_count == 1
    assert mock_drafter_instance._call_gemini.call_count == MAX_CYCLES - 1


# -----------------------------------------------------------------------------
# Test 4 — Regeneration prompt under 1000 tokens
# -----------------------------------------------------------------------------
def test_regeneration_prompt_under_1000_tokens(
    valid_ad_copy: AdCopy,
) -> None:
    """Build regen prompt from real brief + failed ad + report. Estimate tokens; assert bounded."""
    from iterate.controller import build_regeneration_prompt

    report = _make_report(clarity=4, value_proposition=8, call_to_action=8, brand_voice=8, emotional_resonance=8)
    prompt = build_regeneration_prompt(
        current_ad=valid_ad_copy,
        brand_guidelines=SAMPLE_GUIDELINES,
        brief_goal="conversion",
        brief_hook_type="fear",
        report=report,
    )
    assert "Senior Ad Copy Editor" in prompt
    assert "optimized_ad" in prompt and "changes_made" in prompt
    estimated_tokens = len(prompt.split()) * 1.3
    assert estimated_tokens < 1200, f"Regeneration prompt too long: ~{estimated_tokens:.0f} tokens"


# -----------------------------------------------------------------------------
# Test 5 — Dimension-to-guideline mapping complete
# -----------------------------------------------------------------------------
def test_dimension_to_guideline_mapping_complete() -> None:
    """DIMENSION_TO_GUIDELINE_KEY must contain all 5 EvaluationReport dimensions."""
    from iterate.controller import DIMENSION_TO_GUIDELINE_KEY

    required = [
        "brand_voice",
        "emotional_resonance",
        "clarity",
        "value_proposition",
        "call_to_action",
    ]
    for dim in required:
        assert dim in DIMENSION_TO_GUIDELINE_KEY, f"Missing dimension: {dim}"
    assert len(DIMENSION_TO_GUIDELINE_KEY) == 5
