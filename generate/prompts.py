"""
prompts.py
----------
Varsity Ad Engine — Nerdy / Gauntlet — Drafter prompts, constants, sanitization
-------------------------------------------------------------------------------
System prompt builder and injection sanitizer. Imports shared constants from
evaluate/rubrics.py; defines generation-specific constants and all 6 drafter rules.

Key constants / functions:
  DRAFTER_MODEL, FALLBACK_DRAFTER_MODEL, DEFAULT_SEED, BRAND_DIFFERENTIATORS,
  HOOK_TYPES, INJECTION_PATTERNS
  build_drafter_prompt(), sanitize_for_injection()
"""

from __future__ import annotations

import json
import re
from typing import Any

from evaluate.rubrics import (
    CTA_OPTIONS,
    HOOK_MAX_CHARS,
    HEADLINE_MAX_WORDS,
    HEADLINE_MIN_WORDS,
    AdBrief,
)

# -----------------------------------------------------------------------------
# Model constants (PR3 spec — do not redefine rubrics constants)
# -----------------------------------------------------------------------------
DRAFTER_MODEL: str = "gemini-2.5-flash"
FALLBACK_DRAFTER_MODEL: str = "gemini-2.0-flash"
DEFAULT_SEED: int = 42

# -----------------------------------------------------------------------------
# Generation-specific constants (not in rubrics)
# -----------------------------------------------------------------------------
BRAND_DIFFERENTIATORS: list[str] = [
    "Top 5% tutors — rigorously vetted, not an open marketplace",
    "3.4 million learner session ratings",
    "Matched with a tutor in 24 hours based on exact weak areas",
    "1-on-1 personalized matching — not a one-size-fits-all course",
    "200+ point average SAT score improvement",
    "Free diagnostic assessment to start",
]

HOOK_TYPES: list[str] = ["question", "stat", "story", "fear", "empathy"]

INJECTION_PATTERNS: list[str] = [
    r"ignore (previous|above|all) instructions",
    r"forget (everything|your instructions|the above)",
    r"you are now",
    r"new persona",
    r"system prompt",
    r"disregard",
]

FORBIDDEN_WORDS_IN_PROMPT: list[str] = [
    "world-class",
    "cutting-edge",
    "revolutionary",
    "synergy",
    "leverage",
    "paradigm",
    "we have tutors",
    "sign up today",
    "click here",
    "limited time offer",
    "act now",
]


def sanitize_for_injection(
    text: str,
    field_name: str,
    max_chars: int = 500,
) -> dict[str, Any]:
    """
    Scan a string for prompt injection patterns before injecting into LLM prompt.

    Returns success: False if injection detected — caller must NOT proceed.
    Never strips and continues — rejection is the only safe response to injection.

    Args:
        text: Raw string to sanitize.
        field_name: Name of the field for error messages.
        max_chars: Maximum allowed length after sanitization.

    Returns:
        dict: {"success": bool, "data": str | None, "error": str | None}
    """
    if not isinstance(text, str):
        return {
            "success": False,
            "data": None,
            "error": f"Field {field_name} must be a string.",
        }
    lowered = text.lower().strip()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return {
                "success": False,
                "data": None,
                "error": f"Prompt injection detected in {field_name}. Rejected.",
            }
    if len(text) > max_chars:
        return {
            "success": False,
            "data": None,
            "error": f"Field {field_name} exceeds maximum length ({max_chars} chars).",
        }
    return {"success": True, "data": text.strip()[:max_chars], "error": None}


def build_drafter_prompt(
    brief: AdBrief,
    competitive_context: dict,
    brand_guidelines: dict,
) -> str:
    """
    Build the complete Drafter prompt injecting brief, competitive context, and brand guidelines.

    Includes all 6 rules (hook position, approved metrics, synthesis, fear boundary,
    image prompt, forbidden words). Output format: JSON only, no markdown.

    Args:
        brief: Validated AdBrief pydantic object.
        competitive_context: Loaded competitive_context.json as dict.
        brand_guidelines: Loaded brand_guidelines.json as dict.

    Returns:
        str: Complete prompt ready to send to Gemini.
    """
    differentiators_block = "\n".join(f"- {d}" for d in BRAND_DIFFERENTIATORS)
    forbidden_block = ", ".join(FORBIDDEN_WORDS_IN_PROMPT)
    context_str = json.dumps(competitive_context, indent=2) if competitive_context else "{}"
    guidelines_str = json.dumps(brand_guidelines, indent=2) if brand_guidelines else "{}"
    brief_str = brief.model_dump_json(indent=2)

    return f"""You are an elite direct-response copywriter for Varsity Tutors (a Nerdy business).
Generate high-converting Facebook and Instagram ad copy.

BRAND VOICE: Empowering, knowledgeable, approachable, results-focused.
Lead with outcomes, not features. Confident but not arrogant. Expert but not elitist.

AD ANATOMY — generate ALL five components:
1. primary_text: Main copy. Scroll-stopping hook in FIRST LINE. Use one of: {", ".join(HOOK_TYPES)} hook.
2. headline: {HEADLINE_MIN_WORDS}-{HEADLINE_MAX_WORDS} words max. Benefit-driven.
3. description: One sentence max. Secondary reinforcement.
4. cta_button: One of {CTA_OPTIONS}. Match to goal (awareness vs conversion).
5. image_prompt: UGC-style visual scene only. No text, signs, or logos in the image.

RULE 1 — HOOK POSITION (first {HOOK_MAX_CHARS} characters):
The hook must be complete within the first {HOOK_MAX_CHARS} characters of primary_text.
A question mark, period, or exclamation point must appear before character {HOOK_MAX_CHARS}.
Everything after character {HOOK_MAX_CHARS} may be hidden behind "See More" on Facebook.

RULE 2 — APPROVED METRICS ONLY (do not invent statistics):
You may ONLY use these statistics. Do not invent any others:
{differentiators_block}
Do NOT use percentage claims, guarantees, refunds, or discounts not listed above.

RULE 3 — SYNTHESIS:
The product field is a fact sheet, not a script. Extract ONE primary benefit most relevant to this audience.
Numbers survive verbatim: "200+ points", "3.4M ratings", "24 hours", "top 5%". Everything else: synthesize into natural copy.
Write TO the audience. Never reference their demographic behavior in the copy.

RULE 4 — FEAR HOOK BOUNDARY:
Fear hooks are allowed. Shame and catastrophizing are never allowed.
Forbidden words in fear hooks: ruined, failed, doomed, too late, worthless, behind, failure.
Every fear hook MUST pivot to relief or empowerment within 1-2 sentences. The ad must never end on fear.

RULE 5 — IMAGE PROMPT:
image_prompt must describe a UGC-style authentic visual scene.
NEVER request text, words, signs, logos, or brand names rendered in the image.
NEVER use phrases: "a sign that says", "text reading", "words that say", "banner saying", "logo".
Style: authentic, natural lighting, real people, not stock photography.

RULE 6 — FORBIDDEN WORDS:
Never use: {forbidden_block}.

COMPETITIVE CONTEXT:
{context_str}

BRAND GUIDELINES:
{guidelines_str}

AD BRIEF:
{brief_str}

PRIMARY_TEXT LENGTH LIMIT — HARD CONSTRAINT:
primary_text must be 500 characters or fewer. Count characters before outputting.
The Meta ad platform truncates primary_text at 125 characters visible without
"See More" — but the full text must stay under 500 characters total.
If your draft exceeds 500 characters: cut the weakest sentence, not the hook.
Do not summarize — cut. The hook and the CTA must survive any cuts.

OUTPUT FORMAT:
Return ONLY valid JSON. No markdown. No code fences. No explanation.
Exactly these 5 fields:
{{
  "primary_text": "...",
  "headline": "...",
  "description": "...",
  "cta_button": "...",
  "image_prompt": "..."
}}
"""
