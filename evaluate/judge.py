"""
judge.py
--------
Varsity Ad Engine — Nerdy / Gauntlet — Claude Sonnet 4.5 ad evaluator
------------------------------------------------------------------------
Implements the LLM-as-Judge pattern using Anthropic Claude to score every
generated ad across five marketing dimensions. Returns a validated
EvaluationReport with computed average_score, passes_threshold, and
weakest_dimension — never trusting the LLM to calculate these itself.
Anchors imported from rubrics at module level; build_prompt() takes no anchors param.

Drafter uses Gemini 2.0 Flash (Google); Judge uses Claude (Anthropic) — cross-provider
architecture for independent evaluation.

Key classes / functions:
  AdJudge        — Main judge class with Anthropic client
  evaluate_ad()  — Scores one AdCopy, returns structured dict (sync, no async)
  build_prompt() — Injects GOLD/POOR from rubrics into prompt

Author: Varsity Ad Engine
Project: Varsity Ad Engine — Nerdy / Gauntlet AI Program
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import ValidationError

from evaluate.rubrics import (
    GOLD_ANCHOR,
    POOR_ANCHOR,
    AdCopy,
    EvaluationReport,
)

# Judge: Claude (Anthropic). Override via JUDGE_MODEL in .env.
JUDGE_MODEL: str = "claude-sonnet-4-5"
JUDGE_MAX_TOKENS: int = 2048


def _normalize_json_string(raw: str) -> str:
    """Fix common model output mistakes so JSON parses."""
    raw = re.sub(r":\s*True\s*([,}\]])", r": true \1", raw)
    raw = re.sub(r":\s*False\s*([,}\]])", r": false \1", raw)
    raw = re.sub(r":\s*None\s*([,}\]])", r": null \1", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)
    return raw


def _load_judge_api_key() -> str:
    """Load Anthropic API key from .env. Raises EnvironmentError if missing."""
    from dotenv import load_dotenv
    load_dotenv()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set in .env")
    return key


def _get_anthropic_client():
    """Lazy import so tests can patch _call_model without requiring API key."""
    import anthropic
    return anthropic.Anthropic(api_key=_load_judge_api_key())


class AdJudge:
    """
    Scores AdCopy using Claude (Anthropic). build_prompt uses GOLD_ANCHOR and POOR_ANCHOR
    from rubrics.py — no anchors parameter.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = (
            model_name
            or os.environ.get("JUDGE_MODEL")
            or JUDGE_MODEL
        )
        self._client = _get_anthropic_client()

    def build_prompt(self, ad: AdCopy) -> str:
        """
        Build judge prompt with GOLD and POOR anchors from rubrics.py.
        No anchors parameter — imports at module level.
        """
        gold = (
            f"primary_text: {GOLD_ANCHOR['primary_text']}\n"
            f"headline: {GOLD_ANCHOR['headline']}\n"
            f"description: {GOLD_ANCHOR['description']}\n"
            f"cta_button: {GOLD_ANCHOR['cta_button']}"
        )
        poor = (
            f"primary_text: {POOR_ANCHOR['primary_text']}\n"
            f"headline: {POOR_ANCHOR['headline']}\n"
            f"description: {POOR_ANCHOR['description']}\n"
            f"cta_button: {POOR_ANCHOR['cta_button']}"
        )
        ad_block = (
            f"primary_text: {ad.primary_text}\n"
            f"headline: {ad.headline}\n"
            f"description: {ad.description}\n"
            f"cta_button: {ad.cta_button}"
        )
        return f"""You are a rigorous Marketing QA Judge for Varsity Tutors. Most ads fail.
Ruthlessly filter mediocre content. Publishable bar: 7.0/10 average.

SCORE each dimension 1-10:
clarity             | 10=clear in <3s  | 7=mostly clear | 4=re-reading needed | 1=confusing
value_proposition   | 10=specific outcome | 7=decent | 4=generic | 1=feature-only
call_to_action      | 10=specific+urgent | 7=clear | 4=vague | 1=missing
brand_voice         | 10=distinctly VT | 7=on-brand | 4=neutral | 1=generic
emotional_resonance | 10=real motivation | 7=some | 4=rational | 1=flat

CALIBRATION — Gold (8-10):
{gold}

CALIBRATION — Poor (1-4):
{poor}

AD TO SCORE:
{ad_block}

RESPOND ONLY with valid JSON (no markdown, no code block). Keep each rationale to ONE short sentence (under 15 words) so the response is not truncated.
{{
  "clarity": {{"score": <1-10>, "rationale": "<one short sentence>"}},
  "value_proposition": {{"score": <1-10>, "rationale": "<one short sentence>"}},
  "call_to_action": {{"score": <1-10>, "rationale": "<one short sentence>"}},
  "brand_voice": {{"score": <1-10>, "rationale": "<one short sentence>"}},
  "emotional_resonance": {{"score": <1-10>, "rationale": "<one short sentence>"}},
  "average_score": <float>,
  "weakest_dimension": "<one of: clarity, value_proposition, call_to_action, brand_voice, emotional_resonance>",
  "passes_threshold": <true|false>,
  "confidence": "high" or "medium" or "low"
}}
"""

    def _call_model(self, ad: AdCopy) -> str:
        """
        Call Claude and return raw response text (JSON string).
        Extracted so tests can patch this method.
        """
        prompt = self.build_prompt(ad)
        response = self._client.messages.create(
            model=self._model_name,
            max_tokens=JUDGE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        if not response.content or not response.content[0].text:
            return "{}"
        return response.content[0].text.strip()

    def evaluate_ad(self, ad: AdCopy) -> dict[str, Any]:
        """
        Score one AdCopy. Synchronous; returns structured dict. No async, no callbacks.
        For use in main pipeline and Streamlit generator loop.

        Args:
            ad: Validated AdCopy to score.

        Returns:
            dict: {"success": bool, "data": EvaluationReport | None, "error": str | None}
        """
        try:
            raw = self._call_model(ad)
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines)
            raw = raw.strip()
            start = raw.find("{")
            if start >= 0:
                depth = 0
                for i in range(start, len(raw)):
                    if raw[i] == "{":
                        depth += 1
                    elif raw[i] == "}":
                        depth -= 1
                        if depth == 0:
                            raw = raw[start : i + 1]
                            break
            raw = _normalize_json_string(raw)
            data = json.loads(raw)
            report = EvaluationReport.model_validate(data)
            return {"success": True, "data": report, "error": None}
        except json.JSONDecodeError as e:
            try:
                raw2 = self._call_model(ad)
                if raw2.startswith("```"):
                    lines = raw2.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    raw2 = "\n".join(lines)
                raw2 = raw2.strip()
                start = raw2.find("{")
                if start >= 0:
                    depth = 0
                    for i in range(start, len(raw2)):
                        if raw2[i] == "{":
                            depth += 1
                        elif raw2[i] == "}":
                            depth -= 1
                            if depth == 0:
                                raw2 = raw2[start : i + 1]
                                break
                raw2 = _normalize_json_string(raw2)
                data = json.loads(raw2)
                report = EvaluationReport.model_validate(data)
                return {"success": True, "data": report, "error": None}
            except (json.JSONDecodeError, ValidationError, Exception):
                pass
            return {"success": False, "data": None, "error": f"Judge returned invalid JSON: {e}"}
        except ValidationError as e:
            return {"success": False, "data": None, "error": f"Schema validation failed: {e}"}
        except Exception as e:
            return {"success": False, "data": None, "error": f"Unexpected error: {str(e)}"}
