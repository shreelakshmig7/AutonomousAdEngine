"""
drafter.py
----------
Varsity Ad Engine — Nerdy / Gauntlet — Gemini Flash ad drafter
---------------------------------------------------------------
AdDrafter calls Gemini 2.5 Flash (fallback: 2.0 Flash) with structured JSON output.
Pipeline gates: validate_free_text → sanitize_for_injection → build_drafter_prompt → _call_gemini.
Tenacity retry on ResourceExhausted; _clean_json_response before every parse.

Key classes / functions:
  AdDrafter       — Main drafter class
  draft_ad()      — Gate order 1–4, returns structured dict
  _call_gemini()  — API call with retry and generation_config (mock target for tests)
  _clean_json_response() — Strip markdown fences before json.loads
"""

from __future__ import annotations

import json
import os
from typing import Any

import google.api_core.exceptions
from dotenv import load_dotenv
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from evaluate.rubrics import AdCopy, AdBrief
from generate.guardrails import validate_free_text
from generate.prompts import (
    DEFAULT_SEED,
    DRAFTER_MODEL,
    FALLBACK_DRAFTER_MODEL,
    build_drafter_prompt,
    sanitize_for_injection,
)

load_dotenv()


def _load_google_api_key() -> str:
    """Load Google API key from .env. Raises EnvironmentError if missing."""
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise EnvironmentError("GOOGLE_API_KEY not set in .env")
    return key


def _get_genai():
    """Lazy import so tests can patch without requiring API key."""
    import google.generativeai as genai

    genai.configure(api_key=_load_google_api_key())
    return genai


class AdDrafter:
    """
    Generates AdCopy from a brief using Gemini 2.5 Flash. Fallback to 2.0 Flash on rate limit.
    Gates: validate_free_text → sanitize_for_injection → build_drafter_prompt → _call_gemini.
    """

    def __init__(self) -> None:
        self._model_name = os.environ.get("DRAFTER_MODEL") or DRAFTER_MODEL
        self._fallback_model = os.environ.get("FALLBACK_DRAFTER_MODEL") or FALLBACK_DRAFTER_MODEL

    def _clean_json_response(self, raw: str) -> str:
        """
        Strip markdown code fences Gemini sometimes wraps around JSON.
        Called before json.loads() on every response.
        """
        s = raw.strip()
        if s.startswith("```"):
            lines = s.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            s = "\n".join(lines)
        start = s.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(s)):
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                    if depth == 0:
                        s = s[start : i + 1]
                        break
        return s.strip()

    @retry(
        retry=retry_if_exception_type(google.api_core.exceptions.ResourceExhausted),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    def _call_gemini(
        self,
        prompt: str,
        model: str,
        generation_config: dict[str, Any] | None = None,
    ) -> str:
        """
        Make the actual API call. Returns raw response text.
        Separated from draft_ad so retry logic wraps only the API call.
        Tests patch this method and assert on generation_config.
        """
        genai = _get_genai()
        config = generation_config or {}
        # Build SDK GenerationConfig: temperature, response_mime_type, candidate_count
        config_obj = genai.GenerationConfig(
            temperature=config.get("temperature", 0),
            candidate_count=config.get("candidate_count", 1),
            response_mime_type=config.get("response_mime_type", "application/json"),
        )
        gemini_model = genai.GenerativeModel(model)
        response = gemini_model.generate_content(prompt, generation_config=config_obj)
        if not response or not response.text:
            return "{}"
        return response.text

    def draft_ad(
        self,
        brief: AdBrief,
        competitive_context: dict,
        brand_guidelines: dict,
        seed: int = DEFAULT_SEED,
    ) -> dict[str, Any]:
        """
        Generate a structured AdCopy from a brief using Gemini 2.5 Flash.

        Gates: (1) validate_free_text, (2) sanitize_for_injection, (3) build_drafter_prompt, (4) _call_gemini.
        On ResourceExhausted, retries with FALLBACK_DRAFTER_MODEL.

        Args:
            brief: Validated AdBrief.
            competitive_context: Loaded competitive_context.json.
            brand_guidelines: Loaded brand_guidelines.json.
            seed: Deterministic seed (passed in generation_config when SDK supports it).

        Returns:
            dict: {"success": bool, "data": AdCopy | None, "tokens_used": int, "model_used": str | None, "error": str | None}
        """
        # Gate 1: guardrails
        guard_result = validate_free_text(brief)
        if not guard_result["success"]:
            return {
                "success": False,
                "data": None,
                "tokens_used": 0,
                "model_used": None,
                "error": guard_result.get("error", "Guardrails rejected"),
            }

        # Gate 2: sanitize all brief fields
        for field_name, value in brief.model_dump().items():
            sanitized = sanitize_for_injection(str(value), field_name)
            if not sanitized["success"]:
                return {
                    "success": False,
                    "data": None,
                    "tokens_used": 0,
                    "model_used": None,
                    "error": f"Injection detected: {sanitized.get('error', '')}",
                }

        # Gate 3: build prompt
        prompt = build_drafter_prompt(brief, competitive_context, brand_guidelines)

        generation_config = {
            "temperature": 0,
            "candidate_count": 1,
            "response_mime_type": "application/json",
        }

        try:
            try:
                raw = self._call_gemini(
                    prompt, self._model_name, generation_config=generation_config
                )
                model_used = self._model_name
            except google.api_core.exceptions.ResourceExhausted:
                raw = self._call_gemini(
                    prompt, self._fallback_model, generation_config=generation_config
                )
                model_used = self._fallback_model

            cleaned = self._clean_json_response(raw)
            parsed = json.loads(cleaned)

            # Validate — one retry on primary_text length only (schema enforcement, not a cycle)
            try:
                ad = AdCopy.model_validate(parsed)
            except ValidationError as ve:
                errors = ve.errors()
                is_length_error = any(
                    e.get("type") == "string_too_long"
                    and any(
                        loc_item == "primary_text"
                        for loc_item in (e.get("loc") or ())
                    )
                    for e in errors
                )
                if is_length_error:
                    retry_prompt = (
                        "Your previous primary_text was too long. "
                        "Rewrite primary_text to be under 500 characters. "
                        "Keep the hook, the key stat, and the CTA intent intact. "
                        "Return only valid JSON with all 5 fields — no markdown.\n\n"
                        f"Previous output:\n{json.dumps(parsed, indent=2)}"
                    )
                    retry_raw = self._call_gemini(
                        retry_prompt, model_used, generation_config=generation_config
                    )
                    retry_cleaned = self._clean_json_response(retry_raw)
                    retry_parsed = json.loads(retry_cleaned)
                    ad = AdCopy.model_validate(retry_parsed)
                else:
                    raise ve

            return {
                "success": True,
                "data": ad,
                "tokens_used": 0,
                "model_used": model_used,
                "error": None,
            }
        except ValidationError as e:
            return {
                "success": False,
                "data": None,
                "tokens_used": 0,
                "model_used": None,
                "error": f"Schema validation failed: {e}",
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "data": None,
                "tokens_used": 0,
                "model_used": None,
                "error": f"JSON parse failed: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "tokens_used": 0,
                "model_used": None,
                "error": f"Unexpected error: {str(e)}",
            }
