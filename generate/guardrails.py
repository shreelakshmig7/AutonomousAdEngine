"""
guardrails.py
-------------
Varsity Ad Engine — Nerdy / Gauntlet — Off-topic input guardrails (Layer 1)
---------------------------------------------------------------------------
Pattern-matching only — no LLM. Default-deny: input must match at least one
in-scope signal unless blocked earlier by injection or off-topic patterns.

Key functions:
  validate_free_text() — Gate 1 in draft_ad(); returns structured dict.
"""

from __future__ import annotations

import re
from typing import Union

from evaluate.rubrics import AdBrief

# Import injection patterns from single source (prompts.py)
from generate.prompts import INJECTION_PATTERNS

# Out-of-scope / system purpose (not injection)
OUT_OF_SCOPE_MESSAGE: str = (
    "This system generates Varsity Tutors SAT and tutoring ad copy only. "
    "Your request is outside that scope."
)

# Injection attempts — distinct message so callers/tests can distinguish
INJECTION_ATTEMPT_MESSAGE: str = (
    "Prompt injection pattern detected. This system only accepts SAT/tutoring ad briefs. "
    "Remove instruction-override phrases and resubmit."
)

# Legacy alias
SYSTEM_PURPOSE_MESSAGE: str = OUT_OF_SCOPE_MESSAGE

# Known off-topic blocklist — explicit fast rejects (pattern strings only)
OFF_TOPIC_PATTERN_STRINGS: list[str] = [
    r"\bweather\b",
    r"\btalk\s+like\s+a\s+pirate\b",
    r"\bpirate\b.*\b(ad|copy)\b",
    r"\brecipe\b",
    r"\bchocolate\s+cake\b",
    r"\bhow\s+to\s+cook\b",
]

# Default-deny: at least one must match for input to be in scope.
# Omit \bad\b — matches glad/dad; use campaign/brief/audience/hook instead.
IN_SCOPE_SIGNALS: list[str] = [
    r"\bsat\b",
    r"\btest prep\b",
    r"\btutoring\b",
    r"\btutor\b",
    r"\btutors\b",
    r"\btest preparation\b",
    r"\bscore\b",
    r"\bsat prep\b",
    r"\bstudent\b",
    r"\bparent\b",
    r"\bcollege\b",
    r"\bhigh school\b",
    r"\b11th grade\b",
    r"\b10th grade\b",
    r"\b12th grade\b",
    r"\badmission\b",
    r"\badvert\b",
    r"\bcampaign\b",
    r"\bbrief\b",
    r"\baudience\b",
    r"\bconversion\b",
    r"\bawareness\b",
    r"\bhook\b",
    r"\bvarsity\b",
    r"\bnerdy\b",
]


def _normalize_to_text(brief: Union[AdBrief, str]) -> str:
    """Build one lowercase string to scan (AdBrief → concatenated fields)."""
    if isinstance(brief, str):
        return brief.lower().strip()
    return f"{brief.audience} {brief.product} {brief.tone}".lower()


def _reject(
    reason: str,
    message: str,
) -> dict:
    """Unified reject: success False so draft_ad Gate 1 stops; error for pipeline."""
    return {
        "success": False,
        "in_scope": False,
        "reason": reason,
        "error": message,
        "message": message,
    }


def _accept() -> dict:
    return {
        "success": True,
        "in_scope": True,
        "reason": None,
        "error": None,
        "message": None,
    }


def validate_free_text(brief: Union[AdBrief, str]) -> dict:
    """
    Validate free-text input is in scope for SAT ad generation.

    Default-deny: input must match at least one IN_SCOPE_SIGNAL to pass.
    Injection patterns checked first — separate error message.
    Off-topic blocklist second — explicit rejects.
    In-scope check last — rejects everything with no SAT/tutoring signal.

    Args:
        brief: AdBrief or raw string. AdBrief is concatenated to one string for scanning.

    Returns:
        dict: success False → caller must NOT proceed (draft_ad returns early).
        Keys: success, in_scope, reason, error (and message alias for error text).
    """
    try:
        lowered = _normalize_to_text(brief)

        # Priority 1 — Injection patterns
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, lowered):
                return _reject("injection_attempt", INJECTION_ATTEMPT_MESSAGE)

        # Priority 2 — Known off-topic blocklist
        for pattern in OFF_TOPIC_PATTERN_STRINGS:
            if re.search(pattern, lowered, re.IGNORECASE):
                return _reject(f"off_topic_pattern:{pattern}", OUT_OF_SCOPE_MESSAGE)

        # Priority 3 — Default deny: must have at least one in-scope signal
        has_signal = any(re.search(p, lowered) for p in IN_SCOPE_SIGNALS)
        if not has_signal:
            return _reject("no_in_scope_signal", OUT_OF_SCOPE_MESSAGE)

        return _accept()

    except Exception as e:
        return {
            "success": False,
            "in_scope": False,
            "reason": f"validation_error:{e}",
            "error": OUT_OF_SCOPE_MESSAGE,
            "message": OUT_OF_SCOPE_MESSAGE,
        }
