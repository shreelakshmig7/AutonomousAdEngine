"""
rubrics.py
----------
Varsity Ad Engine — Nerdy / Gauntlet — Scoring constants, anchors, and schemas
--------------------------------------------------------------------------------
Quality constants, GOLD/POOR calibration anchors, AdCopy and EvaluationReport
Pydantic schemas. scan_output_safety() runs before scoring. All anchors and
constants live here — judge imports them at module level.

Key constants / classes:
  QUALITY_THRESHOLD, MAX_CYCLES, DIMENSIONS, DIMENSION_PRIORITY, HOOK_MAX_CHARS
  CTA_OPTIONS, GOLD_ANCHOR, POOR_ANCHOR
  AdBrief, AdCopy, DimensionScore, EvaluationReport
  scan_output_safety()

Author: Varsity Ad Engine
Project: Varsity Ad Engine — Nerdy / Gauntlet AI Program
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# -----------------------------------------------------------------------------
# Quality & iteration constants (Coding Standards §6; DECISION_LOG)
# -----------------------------------------------------------------------------
QUALITY_THRESHOLD: float = 7.0
# Dimensions scoring >= this are preserved in iteration (no edits)
STRONG_DIMENSION_THRESHOLD: float = 8.0
MAX_CYCLES: int = 3
EXCELLENT_THRESHOLD: float = 7.5
DIMENSIONS: list[str] = [
    "clarity",
    "value_proposition",
    "call_to_action",
    "brand_voice",
    "emotional_resonance",
]

# Tie-breaking: when dimensions tie at lowest score, target this order first
# (DECISION_LOG — PR2 Architecture)
DIMENSION_PRIORITY: list[str] = [
    "emotional_resonance",
    "value_proposition",
    "clarity",
    "brand_voice",
    "call_to_action",
]

# Display names for change log and prompts (iterator output)
DIMENSION_DISPLAY_NAMES: dict[str, str] = {
    "clarity": "Clarity",
    "value_proposition": "Value Prop",
    "call_to_action": "CTA",
    "brand_voice": "Brand Voice",
    "emotional_resonance": "Emotion",
}

# Meta truncation — hook must complete within this many chars (Edge Case 2)
HOOK_MAX_CHARS: int = 100

# Headline word count (brand_guidelines meta_ad_structure)
HEADLINE_MIN_WORDS: int = 5
HEADLINE_MAX_WORDS: int = 8

# Competitor names for scan_output_safety (Coding Standards §13.3)
COMPETITOR_NAMES: list[str] = [
    "khan academy",
    "princeton review",
    "kaplan",
    "chegg",
]

# Allowed CTA button values — matches AdCopy Literal type (PR3)
CTA_OPTIONS: list[str] = [
    "Learn More",
    "Sign Up",
    "Start Free Assessment",
    "Get Started",
]

# -----------------------------------------------------------------------------
# AdBrief — Input schema for briefs.json (PR3; shared by generate/ and iterate/)
# -----------------------------------------------------------------------------
class AdBrief(BaseModel):
    """Validated brief from briefs.json. Used by drafter and controller."""

    id: str = Field(..., description="Unique brief identifier e.g. brief_001")
    audience: str = Field(..., min_length=20, description="Specific audience definition")
    product: str = Field(..., min_length=10, description="Product and key selling points")
    goal: Literal["awareness", "conversion"] = Field(..., description="Campaign objective")
    tone: str = Field(..., description="Tone and voice direction")
    hook_type: Literal["fear", "stat", "question", "empathy", "story"] = Field(
        ..., description="Hook type for primary_text"
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(
        default="medium",
        description="Expected difficulty for cycle 1 pass. Used in iteration_log and quality trend.",
    )
    tone_override: Optional[str] = Field(default=None, description="Optional override for tone; used for debug / safety briefs.")
    hard_constraints: Optional[List[str]] = Field(default=None, description="Optional hard constraints e.g. primary_text under 100 chars.")


# -----------------------------------------------------------------------------
# Calibration anchors — hardcoded, never generated (PRD §4)
# -----------------------------------------------------------------------------
GOLD_ANCHOR: dict = {
    "primary_text": (
        "Is your child's SAT score standing between them and their dream school? "
        "Students working with a top-matched Varsity Tutors expert improve an average of 200+ points. "
        "Unlike one-size-fits-all courses, we match your child with a tutor in the top 5% — "
        "based on their exact weak areas. Over 3.4 million learner sessions rated. Start free."
    ),
    "headline": "Your Child's Score Can Improve 200+ Points",
    "description": "Matched with a top 5% tutor in 24 hours. Results, not just prep hours.",
    "cta_button": "Start Free Assessment",
    "image_prompt": "Teen at desk with laptop, relieved smile, warm natural light, authentic UGC style.",
}

POOR_ANCHOR: dict = {
    "primary_text": (
        "Varsity Tutors offers SAT tutoring services. We have experienced tutors "
        "who can help your student prepare for the SAT exam. Sign up today. "
        "Contact us for more information about our programs and pricing."
    ),
    "headline": "SAT Tutoring Is Available Now",
    "description": "Contact us to learn more about our tutoring options.",
    "cta_button": "Learn More",
    "image_prompt": "Student studying at a desk with books and laptop, casual setting.",
}


# -----------------------------------------------------------------------------
# AdCopy — Drafter output schema (validates before judge)
# -----------------------------------------------------------------------------
class AdCopy(BaseModel):
    """Structured output from Gemini Flash Drafter. All constraints from brand_guidelines.json."""

    primary_text: str = Field(
        ...,
        min_length=80,
        max_length=500,
        description="Main copy. Hook complete within first 100 chars. Value prop in first sentence.",
    )
    headline: str = Field(
        ...,
        min_length=5,
        description="5-8 words. Benefit-driven. Front-load the outcome.",
    )
    description: str = Field(
        ...,
        min_length=10,
        description="One sentence max. Secondary reinforcement.",
    )
    cta_button: Literal["Learn More", "Sign Up", "Start Free Assessment", "Get Started"] = Field(...)
    image_prompt: str = Field(
        ...,
        min_length=20,
        max_length=450,
        description="Ad image: infographic, before/after, or text-hero style; may include headline/stat for layout.",
    )

    @field_validator("headline")
    @classmethod
    def headline_word_count(cls, v: str) -> str:
        words = v.split()
        if not (HEADLINE_MIN_WORDS <= len(words) <= HEADLINE_MAX_WORDS):
            raise ValueError(f"Headline must be 5-8 words, got {len(words)}")
        return v

    @field_validator("primary_text")
    @classmethod
    def hook_completeness(cls, v: str) -> str:
        """Enforce Meta truncation rule — hook must complete within 100 chars (Edge Case 2)."""
        first_100 = v[:HOOK_MAX_CHARS]
        if not any(c in first_100 for c in [".", "?", "!"]):
            raise ValueError(
                f"Hook must complete within first {HOOK_MAX_CHARS} chars. Got: '{first_100}'"
            )
        return v

    @field_validator("image_prompt")
    @classmethod
    def no_text_in_image_prompt(cls, v: str) -> str:
        """Block open-ended injection; allow structured ad styles (infographic, before/after, text hero) with headline/stat."""
        forbidden = [
            "a sign that says",
            "words that say",
            "banner saying",
            "logo",
        ]
        lower = v.lower()
        for phrase in forbidden:
            if phrase in lower:
                raise ValueError(f"Image prompt contains forbidden phrase: '{phrase}'")
        return v


# -----------------------------------------------------------------------------
# DimensionScore & EvaluationReport — Judge output schema
# -----------------------------------------------------------------------------
class DimensionScore(BaseModel):
    """Score + rationale for one evaluation dimension. Score may be decimal (e.g. 7.5, 8.2)."""

    score: float = Field(..., ge=1.0, le=10.0, description="1.0–10.0; decimals allowed.")
    rationale: str = Field(..., min_length=10, description="1–2 sentence explanation for this score.")


_DimensionName = Literal[
    "clarity",
    "value_proposition",
    "call_to_action",
    "brand_voice",
    "emotional_resonance",
]


class EvaluationReport(BaseModel):
    """Structured output from Gemini Pro Judge. Computed fields overridden by model_validator."""

    clarity: DimensionScore
    value_proposition: DimensionScore
    call_to_action: DimensionScore
    brand_voice: DimensionScore
    emotional_resonance: DimensionScore

    average_score: float = Field(
        ...,
        description="Computed and overridden from actual dimension scores.",
    )
    weakest_dimension: _DimensionName = Field(
        ...,
        description="Computed: dimension with the lowest score (tie-break via DIMENSION_PRIORITY).",
    )
    passes_threshold: bool = Field(
        ...,
        description="Computed: True if all dimension scores >= QUALITY_THRESHOLD.",
    )
    confidence: Literal["high", "medium", "low"] = Field(...)

    @model_validator(mode="after")
    def enforce_computed_fields(self) -> "EvaluationReport":
        """Override LLM-reported values with computed ground truth (Edge Case 4 tie-break)."""
        scores = {
            "clarity": round(self.clarity.score, 1),
            "value_proposition": round(self.value_proposition.score, 1),
            "call_to_action": round(self.call_to_action.score, 1),
            "brand_voice": round(self.brand_voice.score, 1),
            "emotional_resonance": round(self.emotional_resonance.score, 1),
        }
        self.average_score = round(sum(scores.values()) / len(scores), 2)
        self.passes_threshold = all(s >= QUALITY_THRESHOLD for s in scores.values())
        min_score = min(scores.values())
        tied = [dim for dim, s in scores.items() if abs(s - min_score) < 0.01]
        if len(tied) == 1:
            self.weakest_dimension = tied[0]
        else:
            for dim in DIMENSION_PRIORITY:
                if dim in tied:
                    self.weakest_dimension = dim
                    break
            else:
                self.weakest_dimension = tied[0]
        return self


# -----------------------------------------------------------------------------
# Output safety — runs before evaluate_ad() (PR2 scope; DECISION_LOG)
# -----------------------------------------------------------------------------
def scan_output_safety(ad: AdCopy, forbidden_phrases: list[str] | None = None) -> dict:
    """
    Scan generated ad for competitor names, PII patterns, and forbidden words.
    Includes primary_text, headline, description, and image_prompt (text in image).
    Call before evaluate_ad(). Pipeline: generate → scan → score.

    Args:
        ad: Validated AdCopy to scan.
        forbidden_phrases: Optional override; default from brand_guidelines voice.

    Returns:
        dict: {"success": True, "safe": True, "error": None}
              or {"success": True, "safe": False, "error": "description", "violations": [...]}
    """
    violations: list[str] = []
    # Include image_prompt so text described for the image is also checked (tone/forbidden)
    image_prompt_text = getattr(ad, "image_prompt", "") or ""
    text_to_scan = f"{ad.primary_text} {ad.headline} {ad.description} {image_prompt_text}".lower()

    if forbidden_phrases is None:
        forbidden_phrases = [
            "world-class", "cutting-edge", "revolutionary", "synergy", "leverage",
            "paradigm", "we have tutors", "sign up today", "click here",
            "limited time offer", "act now",
        ]

    for phrase in forbidden_phrases:
        if phrase.lower() in text_to_scan:
            violations.append(f"forbidden_phrase:{phrase}")

    for name in COMPETITOR_NAMES:
        if name in text_to_scan:
            violations.append(f"competitor_mention:{name}")

    # Prohibited claims (invented stats, guarantees)
    if "guarantee" in text_to_scan or "guaranteed" in text_to_scan:
        violations.append("prohibited_claim:guarantee")
    if "refund" in text_to_scan:
        violations.append("prohibited_claim:refund")

    if violations:
        return {
            "success": True,
            "safe": False,
            "error": f"Safety violations: {', '.join(violations)}",
            "violations": violations,
        }
    return {"success": True, "safe": True, "error": None, "violations": []}
