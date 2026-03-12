"""
image_generator.py
------------------
Varsity Ad Engine — PR5 — Companion ad image generation (Nano Banana)
----------------------------------------------------------------------
Uses google-genai SDK only for this module (Gemini 2.5 Flash Image).
Model default matches Google blog sample: gemini-2.5-flash-image-preview.
GOOGLE_API_KEY from .env. Saves PNGs under output/images/; publish path only.

Key:
  IMAGE_GEN_MODEL — gemini-2.5-flash-image-preview (configurable via env)
  AdImageGenerator.generate_image() — structured dict, never raises
  _invoke_model() — patchable for tests; extracts inline_data from response parts
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# Stable model id from ListModels — preview id returns 404 on v1beta
IMAGE_GEN_MODEL: str = "gemini-2.5-flash-image"

_SAFE_ID_RE: re.Pattern[str] = re.compile(r"[^a-zA-Z0-9_-]+")


def _sanitize_ad_id(ad_id: str) -> str:
    """
    Reduce ad_id to safe filename stem.

    Args:
        ad_id: Raw id e.g. brief_001_v0.

    Returns:
        str: Sanitized stem for PNG filename.
    """
    s = _SAFE_ID_RE.sub("_", (ad_id or "").strip())[:80]
    return s or "ad"


def _load_google_api_key() -> str:
    """
    Load Google API key from environment.

    Returns:
        str: API key.

    Raises:
        EnvironmentError: If GOOGLE_API_KEY is missing.
    """
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise EnvironmentError("GOOGLE_API_KEY not set in .env")
    return key


class AdImageGenerator:
    """
    Generates one image per passing ad from image_prompt via Flash Image (Nano Banana).
    Only invoked from publish path after threshold pass.
    """

    def __init__(
        self,
        output_dir: str = "output/images",
        model_name: str | None = None,
    ) -> None:
        """
        Initialize generator with output directory and model id.

        Args:
            output_dir: Directory to write PNG files (created if missing).
            model_name: Gemini image model id; default IMAGE_GEN_MODEL or IMAGE_GEN_MODEL env.
        """
        self._output_dir = output_dir
        self._model_name = model_name or os.environ.get("IMAGE_GEN_MODEL") or IMAGE_GEN_MODEL

    def generate_image(self, image_prompt: str, ad_id: str) -> dict[str, Any]:
        """
        Generate image from prompt and save as PNG. Returns structured result only.

        Args:
            image_prompt: UGC-style scene description from AdCopy.
            ad_id: Stable id for filename (e.g. brief_id + variation).

        Returns:
            dict: success bool, data=str path or None, error=str or None.
        """
        if not (image_prompt or "").strip():
            return {
                "success": False,
                "data": None,
                "error": "Empty image_prompt",
            }
        prompt = image_prompt.strip()
        try:
            raw_bytes = self._invoke_model(prompt)
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e),
            }
        if not raw_bytes:
            return {
                "success": False,
                "data": None,
                "error": "No image bytes in model response",
            }
        out_path = Path(self._output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_ad_id(ad_id)
        file_path = out_path / f"{stem}.png"
        try:
            file_path.write_bytes(raw_bytes)
        except OSError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e),
            }
        return {
            "success": True,
            "data": str(file_path),
            "error": None,
        }

    def _invoke_model(self, prompt: str) -> bytes | None:
        """
        Call Gemini 2.5 Flash Image (google-genai) and return raw image bytes.

        Follows Google Developers Blog sample: client.models.generate_content,
        then iterate parts for inline_data.

        Args:
            prompt: Text prompt for image generation.

        Returns:
            bytes or None if no inline image in response.
        """
        from google import genai
        from google.genai import types

        api_key = _load_google_api_key()
        # Client() with no args raises ValueError if GOOGLE_API_KEY not in env — pass explicitly
        client = genai.Client(api_key=api_key)
        # Flash Image returns image parts only when response_modalities includes IMAGE
        config = types.GenerateContentConfig(
            response_modalities=[types.Modality.IMAGE.value],
        )
        # Blog uses contents=[prompt, image] for editing; text-only generation: prompt string
        response = client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=config,
        )
        if not response or not getattr(response, "candidates", None):
            return None
        cand = response.candidates[0]
        content = getattr(cand, "content", None)
        if not content:
            return None
        parts = getattr(content, "parts", None) or []
        for part in parts:
            # Blog: part.inline_data is not None -> part.inline_data.data
            inline = getattr(part, "inline_data", None)
            if inline is not None:
                data = getattr(inline, "data", None)
                if data is not None:
                    return bytes(data)
        return None
