"""
rate_limiter.py
---------------
Shreelakshmi Ad Engine — Shared concurrency controls for API rate limiting.
----------------------------------------------------------------------
Module-level semaphores that gate concurrent API calls to Gemini and
Anthropic. Import and use as context managers around actual HTTP calls
so the pipeline can safely run many variations in parallel without
triggering 429 / ResourceExhausted errors.

Tuneable via environment variables:
  GEMINI_MAX_CONCURRENT   — max parallel Gemini calls (default 10)
  ANTHROPIC_MAX_CONCURRENT — max parallel Anthropic calls (default 8)
"""

from __future__ import annotations

import os
import threading

from dotenv import load_dotenv

load_dotenv()

GEMINI_MAX_CONCURRENT: int = int(os.environ.get("GEMINI_MAX_CONCURRENT", 5))
ANTHROPIC_MAX_CONCURRENT: int = int(os.environ.get("ANTHROPIC_MAX_CONCURRENT", 2))

# Delay (seconds) after each Anthropic API call to stay within token-per-minute limits.
# Anthropic Tier 1: Sonnet 30K TPM / Haiku 50K TPM / all models 50 RPM.
ANTHROPIC_CALL_DELAY: float = float(os.environ.get("ANTHROPIC_CALL_DELAY", 2.0))

gemini_semaphore: threading.Semaphore = threading.Semaphore(GEMINI_MAX_CONCURRENT)
anthropic_semaphore: threading.Semaphore = threading.Semaphore(ANTHROPIC_MAX_CONCURRENT)
