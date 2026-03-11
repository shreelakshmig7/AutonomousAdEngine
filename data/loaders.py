"""
loaders.py
----------
Varsity Ad Engine — Nerdy / Gauntlet — Load briefs and config JSON
------------------------------------------------------------------
Single place for loading briefs, competitive context, and brand guidelines.
Used by manual smoke test, main.py, and app.py. Access named keys only —
do not iterate over all keys (brand_guidelines may contain _comment, _edge_case).
"""

from __future__ import annotations

import json

from evaluate.rubrics import AdBrief


def load_briefs(path: str = "data/briefs.json") -> list[AdBrief]:
    """
    Load and validate all briefs from JSON.

    Args:
        path: Path to briefs.json. Default data/briefs.json.

    Returns:
        list[AdBrief]: Validated briefs. Key "briefs" in JSON; _meta ignored.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    briefs_raw = data.get("briefs", [])
    return [AdBrief.model_validate(b) for b in briefs_raw]


def load_competitive_context(path: str = "data/competitive_context.json") -> dict:
    """
    Load competitive context. Returned as dict for prompt injection.

    Args:
        path: Path to competitive_context.json.

    Returns:
        dict: Full JSON object (research_source, competitors, etc.).
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_brand_guidelines(path: str = "data/brand_guidelines.json") -> dict:
    """
    Load brand guidelines. Returned as dict for prompt injection.

    Do not strip _comment or _edge_case keys — they are semantic signals
    in the prompt. Access named keys only (e.g. voice, approved_differentiators).

    Args:
        path: Path to brand_guidelines.json.

    Returns:
        dict: Full JSON object (brand, voice, hook_guidelines, etc.).
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)
