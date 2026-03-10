"""
conftest.py
-----------
Varsity Ad Engine — Nerdy / Gauntlet — Pytest fixtures and mocks
----------------------------------------------------------------
Mocks Anthropic API key for evaluator tests so they run fully offline.
Judge uses Claude (Anthropic); Drafter uses Gemini (Google).
"""

import pytest
from unittest.mock import patch


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
