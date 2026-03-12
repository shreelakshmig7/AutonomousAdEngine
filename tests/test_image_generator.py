"""
test_image_generator.py
-----------------------
Varsity Ad Engine — PR5 — AdImageGenerator TDD
-----------------------------------------------
Tests mock _invoke_model so no network. Asserts structured return and file write.
"""

import base64
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 1x1 transparent PNG — valid file for assert exists
MINIMAL_PNG_BYTES: bytes = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_generate_image_success_writes_file() -> None:
    """Mock _invoke_model to return PNG bytes — assert success, image_path under output dir."""
    from images.image_generator import AdImageGenerator

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "images"
        gen = AdImageGenerator(output_dir=str(out_dir), model_name="gemini-2.5-flash-image")
        with patch.object(gen, "_invoke_model", return_value=MINIMAL_PNG_BYTES):
            result = gen.generate_image("Parent and teen at table, warm light, UGC style.", "ad_001")
        assert result["success"] is True
        assert result["error"] is None
        path = result["data"]
        assert path is not None
        assert Path(path).exists()
        assert Path(path).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_image_no_bytes_returns_error() -> None:
    """When model returns no image bytes — success False, no file required."""
    from images.image_generator import AdImageGenerator

    with tempfile.TemporaryDirectory() as tmp:
        gen = AdImageGenerator(output_dir=str(Path(tmp) / "images"))
        with patch.object(gen, "_invoke_model", return_value=None):
            result = gen.generate_image("A scene with natural lighting.", "ad_002")
        assert result["success"] is False
        assert result["data"] is None
        assert result["error"] is not None


def test_generate_image_empty_prompt_returns_error() -> None:
    """Empty image_prompt must not call API — structured error."""
    from images.image_generator import AdImageGenerator

    gen = AdImageGenerator(output_dir="output/images")
    result = gen.generate_image("", "ad_003")
    assert result["success"] is False
    assert result["data"] is None
    assert "prompt" in result["error"].lower() or "empty" in result["error"].lower()
