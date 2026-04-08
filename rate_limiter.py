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

GEMINI_MAX_CONCURRENT: int = int(os.environ.get("GEMINI_MAX_CONCURRENT", 7))
ANTHROPIC_MAX_CONCURRENT: int = int(os.environ.get("ANTHROPIC_MAX_CONCURRENT", 5))

gemini_semaphore: threading.Semaphore = threading.Semaphore(GEMINI_MAX_CONCURRENT)
anthropic_semaphore: threading.Semaphore = threading.Semaphore(ANTHROPIC_MAX_CONCURRENT)
