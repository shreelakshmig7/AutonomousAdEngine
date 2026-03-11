"""
conftest.py
-----------
Varsity Ad Engine — Nerdy / Gauntlet — Pytest fixtures and mocks
----------------------------------------------------------------
Mocks Anthropic API key for evaluator tests so they run fully offline.
Judge uses Claude (Anthropic); Drafter uses Gemini (Google).
Shared fixtures for generator and guardrail tests (PR3).
"""

import pytest
from unittest.mock import patch

from evaluate.rubrics import AdBrief


@pytest.fixture(autouse=True)
def mock_judge_api_for_evaluator_tests(request):
    """
    When running test_evaluator, mock _load_judge_api_key so AdJudge()
    can be constructed without ANTHROPIC_API_KEY in .env.
    """
    if "test_evaluator" not in request.module.__name__:
        yield
        return
    with patch("evaluate.judge._load_judge_api_key", return_value="test-key"):
        yield


# -----------------------------------------------------------------------------
# PR3 — Shared fixtures for test_generator and test_guardrails
# -----------------------------------------------------------------------------

@pytest.fixture
def valid_ad_dict() -> dict:
    """Valid AdCopy-shaped dict for mocking Gemini responses. Single source of truth."""
    return {
        "primary_text": (
            "Is your child's SAT score standing between them and their dream school? "
            "Students improve 200+ points with a top 5% matched tutor."
        ),
        "headline": "Raise Your SAT Score 200 Points",
        "description": "Matched with a top 5% tutor in 24 hours.",
        "cta_button": "Start Free Assessment",
        "image_prompt": (
            "Parent and teen at kitchen table, teen smiling at laptop, "
            "warm natural lighting, authentic UGC style."
        ),
    }


@pytest.fixture
def sample_brief() -> AdBrief:
    """Valid AdBrief for generator and guardrail tests."""
    return AdBrief(
        id="brief_001",
        audience="Parents of 11th graders in the Southeast with household income $75K-$150K",
        product="SAT 1-on-1 tutoring with free diagnostic assessment",
        goal="conversion",
        tone="empathetic and urgent",
        hook_type="fear",
        difficulty="medium",
    )
