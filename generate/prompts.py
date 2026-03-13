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
# Fallback when Gemini rate-limits: 2.0-flash has free-tier limit 0 — use Claude Haiku instead
FALLBACK_DRAFTER_MODEL: str = "claude-haiku-4-5-20251001"
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
    variation_index: int | None = None,
    total_variations: int | None = None,
) -> str:
    """
    Build the complete Drafter prompt injecting brief, competitive context, and brand guidelines.

    Includes all 6 rules (hook position, approved metrics, synthesis, fear boundary,
    image prompt, forbidden words). Output format: JSON only, no markdown.

    Args:
        brief: Validated AdBrief pydantic object.
        competitive_context: Loaded competitive_context.json as dict.
        brand_guidelines: Loaded brand_guidelines.json as dict.
        variation_index: Optional 0-based index of this variation (for diversity instruction).
        total_variations: Optional total number of variations per brief.

    Returns:
        str: Complete prompt ready to send to Gemini.
    """
    differentiators_block = "\n".join(f"- {d}" for d in BRAND_DIFFERENTIATORS)
    forbidden_block = ", ".join(FORBIDDEN_WORDS_IN_PROMPT)
    context_str = json.dumps(competitive_context, indent=2) if competitive_context else "{}"
    guidelines_str = json.dumps(brand_guidelines, indent=2) if brand_guidelines else "{}"
    brief_str = brief.model_dump_json(indent=2)

    variation_instruction = ""
    if variation_index is not None and total_variations is not None and total_variations > 1:
        n = variation_index + 1
        variation_instruction = (
            f"\n\nVARIATION DIVERSITY: This is variation {n} of {total_variations} for this brief. "
            "Generate a DISTINCT headline and primary text — use a different hook angle, framing, or benefit so this ad is clearly different from other variations (e.g. different question, stat, or story lead). Do not repeat the same headline or opening line across variations."
        )

    tone_section = ""
    if getattr(brief, "tone_override", None):
        tone_section = f"""TONE OVERRIDE — OVERRIDES RULE 4 FOR THIS BRIEF ONLY:
{brief.tone_override}
This brief is intentionally testing the evaluation system. Follow this tone exactly.

"""

    if getattr(brief, "hard_constraints", None):
        constraints_text = "\n".join(f"- {c}" for c in brief.hard_constraints)
        length_section = f"""PRIMARY_TEXT HARD CONSTRAINTS — MUST FOLLOW EXACTLY:
{constraints_text}
These override all other length rules above."""
    else:
        length_section = """PRIMARY_TEXT LENGTH LIMIT — HARD CONSTRAINT:
primary_text must be 500 characters or fewer. Count characters before outputting.
The Meta ad platform truncates primary_text at 125 characters visible without
"See More" — but the full text must stay under 500 characters total.
If your draft exceeds 500 characters: cut the weakest sentence, not the hook.
Do not summarize — cut. The hook and the CTA must survive any cuts."""

    return f"""You are an elite direct-response copywriter for Varsity Tutors (a Nerdy business).
Generate high-converting Facebook and Instagram ad copy.{variation_instruction}

BRAND VOICE: Empowering, knowledgeable, approachable, results-focused.
Lead with outcomes, not features. Confident but not arrogant. Expert but not elitist.

AD ANATOMY — generate ALL five components:
1. primary_text: Main copy. Scroll-stopping hook in FIRST LINE. Use one of: {", ".join(HOOK_TYPES)} hook.
2. headline: {HEADLINE_MIN_WORDS}-{HEADLINE_MAX_WORDS} words max. Benefit-driven.
3. description: One sentence max. Secondary reinforcement.
4. cta_button: One of {CTA_OPTIONS}. Match to goal (awareness vs conversion).
5. image_prompt: Describe ONE of these ad image styles (match to your headline/stat):
   - Infographic: Split-panel illustration. Left = student success (grades, progress report, trophy). Right = same student stressed (SAT score on screen, e.g. 1180). Center banner with the key question or stat (e.g. "3.8 GPA But 1180 SAT?"). Clean cartoon/educational style, blue accents, no photorealism.
   - Before/after: Realistic photo. Person (e.g. young woman or student) holding two SAT score reports side by side — one "Before" (e.g. 1170), one "After" (e.g. 1410). Natural lighting, home or study setting. Headline can appear below the image in the ad; image focuses on the score comparison.
   - Text hero: Minimal background (soft grey or lavender). Bold headline and 2–4 short stat/benefit lines (e.g. "8 weeks away.", "200+ points.", "Start this week."). Checkmark or bullet accents. Brand "Varsity Tutors" at bottom. Modern, high-contrast text, no photo.
   Include the exact headline or key stat/CTA to be shown in the image so the layout is clear.

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

RULE 5 — IMAGE PROMPT (ad creative styles):
image_prompt must describe ONE of: Infographic (split-panel, key question/stat in center), Before/after (person with two score reports), or Text hero (bold headline + stat lines + CTA on minimal background).
You MAY include the exact headline, key stat (e.g. "200+ points"), or CTA line to be displayed in the image so the generator can match the reference ad look.
Do NOT use vague injection phrases: "a sign that says", "text reading", "words that say". Do use: "center banner with the text:", "headline:", "display the stat:", "score report showing 1170 and 1410".
Style: polished ad creative; infographic = clean illustration; before/after = natural photo; text hero = minimal background, bold type.

RULE 6 — FORBIDDEN WORDS:
Never use: {forbidden_block}.

COMPETITIVE CONTEXT:
{context_str}

BRAND GUIDELINES:
{guidelines_str}

AD BRIEF:
{brief_str}

{tone_section}{length_section}

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
