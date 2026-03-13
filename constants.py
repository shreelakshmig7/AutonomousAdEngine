"""
constants.py
------------
Varsity Ad Engine — Pipeline and timeout constants.
--------------------------------------------------
Shared constants for main pipeline (e.g. variation run timeout).
"""

# Per-variation timeout for run_brief (draft + judge + regen cycles)
VARIATION_RUN_TIMEOUT_SECONDS: int = 300
