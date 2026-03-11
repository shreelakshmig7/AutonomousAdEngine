"""
generate/
---------
Varsity Ad Engine — Nerdy / Gauntlet — Ad Drafter package
----------------------------------------------------------
Contains the Drafter agent (Gemini 2.5 Flash), guardrails, and
prompt templates used to generate ad copy from briefs.

Modules:
  guardrails.py — validate_free_text (off-topic rejection, pattern match only)
  prompts.py    — System prompt templates, constants, sanitization
  drafter.py    — AdDrafter class, Gemini Flash calls, fallback logic
"""
