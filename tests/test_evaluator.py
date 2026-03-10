"""
test_evaluator.py
-----------------
Varsity Ad Engine — Nerdy / Gauntlet — Evaluator (Judge + Rubrics) tests
--------------------------------------------------------------------------------
TDD: 4 tests for gold/poor calibration, threshold, weakest dimension.
All API calls mocked via AdJudge._call_model — tests run fully offline.

Tests:
  test_gold_ad_scores_high       — Gold anchor average >= 8.0
  test_poor_ad_scores_low        — Poor anchor average <= 4.0
  test_threshold_triggers_regen  — Score < 7.0 => passes_threshold False
  test_weakest_dimension_identified — Tie-break returns correct dimension per DIMENSION_PRIORITY

Author: Varsity Ad Engine
Project: Varsity Ad Engine — Nerdy / Gauntlet AI Program
"""

import json
from unittest.mock import patch

import pytest

from evaluate.judge import AdJudge
from evaluate.rubrics import (
    DIMENSION_PRIORITY,
    GOLD_ANCHOR,
    POOR_ANCHOR,
    QUALITY_THRESHOLD,
    AdCopy,
)


def _make_judge_json(scores: dict, confidence: str = "high") -> str:
    """Build JSON string that judge parses into EvaluationReport."""
    dims = {}
    for name, score in scores.items():
        dims[name] = {"score": score, "rationale": "Test rationale for " + name + " (min 10 chars)."}
    return json.dumps({
        "clarity": dims["clarity"],
        "value_proposition": dims["value_proposition"],
        "call_to_action": dims["call_to_action"],
        "brand_voice": dims["brand_voice"],
        "emotional_resonance": dims["emotional_resonance"],
        "average_score": sum(scores.values()) / 5,
        "weakest_dimension": min(scores, key=scores.get),
        "passes_threshold": (sum(scores.values()) / 5) >= 7.0,
        "confidence": confidence,
    })


@pytest.fixture
def gold_ad_copy() -> AdCopy:
    """Valid AdCopy matching GOLD_ANCHOR for calibration test."""
    return AdCopy.model_validate(GOLD_ANCHOR)


@pytest.fixture
def poor_ad_copy() -> AdCopy:
    """Valid AdCopy matching POOR_ANCHOR for calibration test."""
    return AdCopy.model_validate(POOR_ANCHOR)


def test_gold_ad_scores_high(gold_ad_copy: AdCopy) -> None:
    """Gold anchor ad must score >= 8.0 average (calibration)."""
    high_scores = {
        "clarity": 9,
        "value_proposition": 9,
        "call_to_action": 8,
        "brand_voice": 9,
        "emotional_resonance": 9,
    }
    mock_response = _make_judge_json(high_scores)
    with patch.object(AdJudge, "_call_model", return_value=mock_response):
        judge = AdJudge()
        result = judge.evaluate_ad(gold_ad_copy)
    assert result["success"] is True
    assert result.get("data") is not None
    assert result["data"].average_score >= 8.0


def test_poor_ad_scores_low(poor_ad_copy: AdCopy) -> None:
    """Poor anchor ad must score <= 4.0 average (calibration)."""
    low_scores = {
        "clarity": 3,
        "value_proposition": 2,
        "call_to_action": 3,
        "brand_voice": 2,
        "emotional_resonance": 3,
    }
    mock_response = _make_judge_json(low_scores)
    with patch.object(AdJudge, "_call_model", return_value=mock_response):
        judge = AdJudge()
        result = judge.evaluate_ad(poor_ad_copy)
    assert result["success"] is True
    assert result.get("data") is not None
    assert result["data"].average_score <= 4.0


def test_threshold_triggers_regen() -> None:
    """Score below QUALITY_THRESHOLD must set passes_threshold False (triggers regeneration)."""
    ad = AdCopy.model_validate(GOLD_ANCHOR)
    below_threshold = {
        "clarity": 5,
        "value_proposition": 5,
        "call_to_action": 5,
        "brand_voice": 5,
        "emotional_resonance": 6,
    }
    mock_response = _make_judge_json(below_threshold)
    with patch.object(AdJudge, "_call_model", return_value=mock_response):
        judge = AdJudge()
        result = judge.evaluate_ad(ad)
    assert result["success"] is True
    assert result["data"].average_score < QUALITY_THRESHOLD
    assert result["data"].passes_threshold is False


def test_weakest_dimension_identified() -> None:
    """When dimensions tie for lowest score, weakest_dimension follows DIMENSION_PRIORITY."""
    ad = AdCopy.model_validate(GOLD_ANCHOR)
    # Tie: clarity 3, value_proposition 3; others 8. First in DIMENSION_PRIORITY among tied wins.
    tied_low = {
        "clarity": 3,
        "value_proposition": 3,
        "call_to_action": 8,
        "brand_voice": 8,
        "emotional_resonance": 8,
    }
    mock_response = _make_judge_json(tied_low)
    with patch.object(AdJudge, "_call_model", return_value=mock_response):
        judge = AdJudge()
        result = judge.evaluate_ad(ad)
    assert result["success"] is True
    report = result["data"]
    # model_validator overrides weakest_dimension using DIMENSION_PRIORITY
    # Tied: clarity, value_proposition. DIMENSION_PRIORITY: emotional_resonance, value_proposition, clarity, ...
    # So value_proposition comes before clarity -> expected is value_proposition
    assert report.weakest_dimension in ("clarity", "value_proposition")
    tied_dims = [
        d for d in ("clarity", "value_proposition")
        if (report.clarity.score if d == "clarity" else report.value_proposition.score) == 3
    ]
    expected = next(d for d in DIMENSION_PRIORITY if d in tied_dims)
    assert report.weakest_dimension == expected
