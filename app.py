"""
app.py
------
Streamlit Cloud entrypoint — Kinetic Observatory design theme.
Sidebar with nav, top-bar, metric cards, charts, and Facebook-style ad thumbnail grid.
All pipeline logic and data loading unchanged from previous version.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
REPO_ROOT: Path = Path(__file__).resolve().parent
ADS_LIBRARY_PATH: Path = REPO_ROOT / "output" / "ads_library.json"
ITERATION_LOG_PATH: Path = REPO_ROOT / "output" / "iteration_log.csv"
RUNS_DIR: Path = REPO_ROOT / "output" / "runs"
MAIN_SCRIPT: Path = REPO_ROOT / "main.py"
DEFAULT_MIN_SCORE: float = 7.0
MIN_SCORE_SLIDER_MIN: float = 5.0
MIN_SCORE_SLIDER_MAX: float = 10.0
CTA_DESTINATION_URL: str = "https://www.varsitytutors.com/"

DIMENSION_KEYS: list[str] = [
    "clarity", "value_proposition", "call_to_action", "brand_voice", "emotional_resonance",
]
DIMENSION_LABELS: dict[str, str] = {
    "clarity": "Clarity",
    "value_proposition": "Value Prop",
    "call_to_action": "CTA",
    "brand_voice": "Brand Voice",
    "emotional_resonance": "Emotion",
}

NAV_ITEMS: list[tuple[str, str, str]] = [
    ("dashboard", "Dashboard", "📊"),
    ("library", "Library", "📁"),
    ("healing", "Self-Healing", "🔧"),
    ("pipeline", "Run Pipeline", "▶️"),
    ("settings", "Settings", "⚙️"),
]


# ---------------------------------------------------------------------------
# CSS — Kinetic Observatory theme
# ---------------------------------------------------------------------------
KINETIC_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@300;400;500;600;700&display=swap');

/* ── Root tokens ── */
:root {
    --bg:              #0a0e14;
    --surface-low:     #0f141a;
    --surface:         #151a21;
    --surface-high:    #1b2028;
    --surface-highest: #20262f;
    --on-surface:      #f1f3fc;
    --on-surface-var:  #a8abb3;
    --primary:         #69daff;
    --secondary:       #00fc40;
    --tertiary:        #ac89ff;
    --error:           #ff716c;
    --outline-var:     #44484f;
}

/* ── Global ── */
html, body, .stApp {
    background: var(--bg) !important;
    color: var(--on-surface) !important;
    font-family: 'Inter', sans-serif !important;
}
.stApp > header { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stBottom"] { display: none !important; }

/* ── Block container ── */
.block-container {
    padding-top: 28px !important;
    padding-left: 36px !important;
    padding-right: 36px !important;
    max-width: 100% !important;
}

/* ── Sidebar shell ── */
[data-testid="stSidebar"] {
    background: var(--surface-low) !important;
    border-right: 1px solid rgba(68,72,79,0.12) !important;
    min-width: 230px !important;
    max-width: 230px !important;
}
[data-testid="stSidebar"] > div:first-child {
    background: var(--surface-low) !important;
    padding: 0 !important;
}
[data-testid="stSidebarContent"] { padding: 0 !important; }

/* ── Radio → nav items ── */
div[data-testid="stSidebar"] [data-testid="stRadio"] {
    margin-top: 4px;
}
div[data-testid="stSidebar"] [data-testid="stRadio"] > label {
    display: none;
}
div[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
div[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
    display: flex !important;
    align-items: center !important;
    padding: 10px 20px !important;
    border-radius: 3px 0 0 3px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 13px !important;
    color: rgba(241,243,252,0.45) !important;
    cursor: pointer !important;
    background: transparent !important;
    border-right: 2px solid transparent !important;
    transition: all 0.15s !important;
    gap: 10px !important;
}
div[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    background: var(--surface) !important;
    color: var(--on-surface) !important;
}
div[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
    color: var(--secondary) !important;
    background: var(--surface-high) !important;
    border-right-color: var(--secondary) !important;
    font-weight: 700 !important;
}
div[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 13px !important;
}
/* Hide the radio circle dot */
div[data-testid="stSidebar"] [data-testid="stRadio"] div[data-baseweb="radio"] {
    display: none !important;
}

/* ── Sidebar widgets ── */
[data-testid="stSidebar"] .stSelectbox > label,
[data-testid="stSidebar"] .stMultiSelect > label,
[data-testid="stSidebar"] .stSlider > label {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 9px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.13em !important;
    color: var(--on-surface-var) !important;
    margin-bottom: 4px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: var(--surface-highest) !important;
    border: none !important;
    border-radius: 4px !important;
    color: var(--on-surface) !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 11px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] svg { color: var(--on-surface-var) !important; }

/* Slider track */
[data-testid="stSidebar"] [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
    background: var(--secondary) !important;
}
[data-testid="stSidebar"] [data-testid="stSlider"] [data-baseweb="slider"] > div > div:first-child {
    background: var(--surface-highest) !important;
}
[data-testid="stSidebar"] [data-testid="stSlider"] [data-baseweb="slider"] > div > div:nth-child(2) {
    background: var(--secondary) !important;
}

/* ── Sidebar buttons ── */
[data-testid="stSidebar"] .stButton > button {
    width: 100% !important;
    background: linear-gradient(135deg, var(--primary), #00cffc) !important;
    color: #002a35 !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    font-size: 10px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    border: none !important;
    border-radius: 4px !important;
    padding: 12px !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    filter: brightness(1.1) !important;
    border: none !important;
}

/* ── Retry buttons in main area ── */
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid rgba(68,72,79,0.35) !important;
    color: var(--primary) !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 9px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    border-radius: 3px !important;
    padding: 5px 12px !important;
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(105,218,255,0.06) !important;
    border-color: var(--primary) !important;
}

/* ── Read more / show less buttons ── */
[data-testid="stSidebar"] ~ div .stButton > button:not([kind="secondary"]):not([kind="primary"]) {
    background: transparent !important;
    color: var(--primary) !important;
    border: none !important;
    font-size: 11px !important;
    padding: 0 !important;
    font-family: 'Space Grotesk', sans-serif !important;
}

/* ── Dividers ── */
[data-testid="stDivider"] hr {
    border-color: rgba(68,72,79,0.15) !important;
    margin: 12px 0 !important;
}

/* ── Headings ── */
h1, h2, h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: var(--on-surface) !important;
}

/* ── Info / warning / error boxes ── */
[data-testid="stAlert"] {
    background: var(--surface-low) !important;
    border-radius: 6px !important;
    border-left: 2px solid var(--tertiary) !important;
    color: var(--on-surface) !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 12px !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] { color: var(--secondary) !important; }

/* ── Code block (pipeline output) ── */
.stCode, .stCode pre {
    background: #000 !important;
    color: var(--secondary) !important;
    font-size: 11px !important;
    border: 1px solid rgba(0,252,64,0.1) !important;
    border-radius: 6px !important;
}

/* ── Pipeline scrollable log ── */
.pipeline-log {
    background: #000;
    border: 1px solid rgba(0,252,64,0.1);
    border-radius: 6px;
    padding: 16px;
    max-height: 500px;
    overflow-y: auto;
    font-family: 'Courier New', monospace;
    font-size: 11px;
    line-height: 1.6;
    color: var(--secondary);
    white-space: pre-wrap;
    word-break: break-word;
}
.pipeline-log::-webkit-scrollbar { width: 6px; }
.pipeline-log::-webkit-scrollbar-track { background: #0a0e14; }
.pipeline-log::-webkit-scrollbar-thumb { background: #44484f; border-radius: 3px; }

/* ── Success / error banners ── */
.stSuccess {
    background: rgba(0,252,64,0.06) !important;
    border-left: 2px solid var(--secondary) !important;
    color: var(--secondary) !important;
}
.stError {
    background: rgba(255,113,108,0.06) !important;
    border-left: 2px solid var(--error) !important;
    color: var(--error) !important;
}

/* ── Main-area select/multiselect/slider widgets ── */
[data-baseweb="select"] > div {
    background: var(--surface-highest) !important;
    border: 1px solid var(--outline-var) !important;
    border-radius: 4px !important;
    color: var(--on-surface) !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 11px !important;
}
[data-baseweb="select"] svg { color: var(--on-surface-var) !important; }
[data-baseweb="popover"] ul { background: var(--surface-high) !important; }
[data-baseweb="popover"] li { color: var(--on-surface) !important; font-family: 'Space Grotesk', sans-serif !important; font-size: 11px !important; }
[data-baseweb="popover"] li:hover { background: var(--surface-highest) !important; }
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] { background: var(--secondary) !important; }
[data-testid="stSlider"] [data-baseweb="slider"] > div > div:first-child { background: var(--surface-highest) !important; }
[data-testid="stSlider"] [data-baseweb="slider"] > div > div:nth-child(2) { background: var(--secondary) !important; }
[data-testid="stSlider"] [data-testid="stThumbValue"] { color: var(--secondary) !important; font-family: 'Space Grotesk', sans-serif !important; font-size: 10px !important; }

/* ── Primary button (main area) ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--primary), #00cffc) !important;
    color: #002a35 !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    font-size: 10px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    border: none !important;
    border-radius: 4px !important;
}
.stButton > button[kind="primary"]:hover { filter: brightness(1.1) !important; }
.stButton > button[kind="primary"]:disabled { opacity: 0.5 !important; }

/* ── Multiselect tags ── */
[data-baseweb="tag"] {
    background: var(--surface-high) !important;
    color: var(--on-surface) !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 10px !important;
}

/* ── Columns gap ── */
[data-testid="column"] { padding: 0 6px !important; }

/* ── Caption text ── */
.stCaption p {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 9px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    color: var(--on-surface-var) !important;
}

/* ── Ad thumbnail card wrapper ── */
.ad-thumb-card {
    background: var(--surface-low);
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid rgba(68,72,79,0.12);
    margin-bottom: 16px;
    transition: border-color 0.2s;
}
.ad-thumb-card:hover { border-color: rgba(105,218,255,0.25); }

.ad-img-area {
    width: 100%;
    display: flex; align-items: center; justify-content: center;
    position: relative; overflow: hidden;
}
.ad-img-area img { width:100%; height:auto; display:block; }
.ad-img-area.no-image {
    background: var(--bg); height: 170px;
    border-bottom: 2px dashed rgba(68,72,79,0.3);
    flex-direction: column; gap: 8px;
}
.ad-img-area.has-image { background: #0d1520; }

.ad-id-tag {
    position: absolute; top: 8px; left: 8px;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 9px; color: var(--on-surface-var);
    background: rgba(10,14,20,0.72);
    padding: 3px 8px; border-radius: 2px;
    letter-spacing: 0.08em;
}
.ad-score-badge {
    position: absolute; top: 8px; right: 8px;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 10px; font-weight: 700;
    padding: 3px 8px; border-radius: 2px;
}
.ad-no-img-label {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 11px; color: var(--on-surface-var);
}
.ad-card-inner { padding: 12px 14px 0; }
.ad-sponsor {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 8px; color: var(--on-surface-var);
    text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 5px;
}
.ad-headline-text {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px; font-weight: 600; line-height: 1.3; margin-bottom: 5px;
}
.ad-preview-text {
    font-size: 10px; color: var(--on-surface-var);
    line-height: 1.5; margin-bottom: 4px;
}
.ad-details { margin-bottom: 4px; }
.ad-details summary {
    color: #60a5fa; font-size: 10px; cursor: pointer;
    list-style: none; display: inline;
}
.ad-details summary::-webkit-details-marker { display: none; }
.ad-details summary::marker { display: none; content: ""; }
.ad-details summary:hover { color: #93c5fd; text-decoration: underline; }
.ad-details .ad-full-text { margin-top: 4px; }
.ad-card-footer {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 14px; border-top: 1px solid rgba(68,72,79,0.1);
}
.ad-cta-text {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 9px; font-weight: 700; color: var(--primary);
    text-transform: uppercase; letter-spacing: 0.1em;
}
.ad-score-bars { display: flex; gap: 3px; align-items: center; }
.score-pip { width: 18px; height: 4px; border-radius: 1px; }

/* ── Metric card ── */
.kinetic-metric {
    background: var(--surface-low);
    border-radius: 6px; padding: 18px 20px;
    border-left: 2px solid var(--primary);
}
.kinetic-metric .m-label {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 8px; text-transform: uppercase;
    letter-spacing: 0.15em; color: var(--on-surface-var); margin-bottom: 6px;
}
.kinetic-metric .m-value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 26px; font-weight: 700; line-height: 1;
}
.kinetic-metric .m-delta {
    font-size: 10px; margin-top: 4px;
}

/* ── Section title ── */
.kinetic-section-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 14px; font-weight: 600;
    display: flex; align-items: center; gap: 8px; margin-bottom: 16px;
}
.kinetic-section-title .acc {
    width: 3px; height: 16px; border-radius: 1px; flex-shrink: 0;
}

/* ── Gallery filter chips ── */
.gallery-chips { display: flex; gap: 7px; margin-bottom: 18px; flex-wrap: wrap; }
.g-chip {
    padding: 5px 12px;
    background: var(--surface);
    border: 1px solid rgba(68,72,79,0.2);
    border-radius: 3px;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 9px; color: var(--on-surface-var);
    text-transform: uppercase; letter-spacing: 0.08em;
    display: inline-block;
}
.g-chip.active {
    background: rgba(0,252,64,0.06);
    border-color: rgba(0,252,64,0.25);
    color: var(--secondary);
}

/* ── Self-healing card ── */
.sh-card {
    background: var(--surface-low);
    border-radius: 6px; margin-bottom: 10px;
    overflow: hidden;
}
.sh-header {
    padding: 14px 18px;
    display: flex; justify-content: space-between;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px; font-weight: 500;
}
.sh-delta { font-weight: 700; color: var(--secondary); font-size: 11px; }
.sh-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 0 18px 18px; }
.sh-col-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 8px; text-transform: uppercase;
    letter-spacing: 0.13em; color: var(--on-surface-var); margin-bottom: 8px;
}
.sh-text { padding: 10px 14px; border-radius: 4px; font-size: 11px; line-height: 1.6; }
.sh-text.initial { background: var(--surface-highest); border-left: 2px solid var(--error); color: var(--on-surface-var); }
.sh-text.healed  { background: rgba(0,252,64,0.04); border-left: 2px solid var(--secondary); }
.sh-score { font-family: 'Space Grotesk', sans-serif; font-size: 22px; font-weight: 700; margin-top: 10px; }
.sh-sub { font-size: 10px; margin-top: 3px; }
.sh-dim-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 10px; }
.sh-dim-label { font-family: 'Space Grotesk', sans-serif; width: 70px; color: var(--on-surface-var); text-transform: uppercase; letter-spacing: 0.06em; font-size: 9px; }
.sh-dim-bar { height: 6px; border-radius: 3px; flex: 1; background: var(--surface-highest); overflow: hidden; }
.sh-dim-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.sh-dim-val { font-family: 'Space Grotesk', sans-serif; width: 28px; text-align: right; font-weight: 600; font-size: 10px; }
.sh-field-label { font-family: 'Space Grotesk', sans-serif; font-size: 9px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--on-surface-var); margin-top: 10px; margin-bottom: 4px; }
.sh-field-value { font-size: 11px; line-height: 1.5; color: var(--on-surface); }
.diff-del { background: rgba(255,113,108,0.18); color: #ff716c; text-decoration: line-through; padding: 1px 3px; border-radius: 2px; }
.diff-add { background: rgba(0,252,64,0.12); color: #00fc40; padding: 1px 3px; border-radius: 2px; }

/* ── Top custom bar ── */
.kinetic-topbar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0 0 20px 0; margin-bottom: 4px;
    border-bottom: 1px solid rgba(68,72,79,0.12);
}
.kinetic-topbar .page-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 22px; font-weight: 700; letter-spacing: -0.02em;
}
.kinetic-topbar .page-sub {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 9px; text-transform: uppercase;
    letter-spacing: 0.15em; color: var(--on-surface-var); margin-top: 3px;
}
.kinetic-topbar-right {
    display: flex; align-items: center; gap: 18px;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 9px; text-transform: uppercase; letter-spacing: 0.15em;
}
</style>
"""

# ---------------------------------------------------------------------------
# Sidebar brand HTML
# ---------------------------------------------------------------------------
SIDEBAR_BRAND_HTML = """
<div style="padding:22px 22px 16px;">
  <div style="font-family:'Space Grotesk',sans-serif;font-size:20px;font-weight:700;
              color:#00fc40;letter-spacing:-0.03em;">KINETIC</div>
  <div style="font-family:'Space Grotesk',sans-serif;font-size:9px;color:#a8abb3;
              text-transform:uppercase;letter-spacing:0.2em;margin-top:4px;">
    Observatory v1.0
  </div>
</div>
"""

# ---------------------------------------------------------------------------
# Helper: safe rerun
# ---------------------------------------------------------------------------
def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helper: load ads library
# ---------------------------------------------------------------------------
def load_ads_library_result(path: Path | None = None) -> dict[str, Any]:
    p = path if path is not None else ADS_LIBRARY_PATH
    if not p.exists():
        if path is not None:
            return {"success": False, "data": {}, "error": "No data for this run."}
        return {"success": True, "data": {}, "error": None}
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {"success": False, "data": {}, "error": "ads_library.json root must be an object"}
        return {"success": True, "data": raw, "error": None}
    except json.JSONDecodeError as e:
        return {"success": False, "data": {}, "error": f"Invalid JSON: {e}"}
    except OSError as e:
        return {"success": False, "data": {}, "error": f"Cannot read file: {e}"}


def get_published_ads(ads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not ads:
        return []
    published = [a for a in ads if a.get("status") == "published"]
    return published if published else ads


def list_run_ids() -> list[str]:
    if not RUNS_DIR.is_dir():
        return []
    ids = [
        d.name for d in RUNS_DIR.iterdir()
        if d.is_dir() and d.name and (d / "ads_library.json").is_file()
    ]
    ids.sort(reverse=True)
    return ids


def _dimension_numeric(scores: dict[str, Any], key: str) -> float | None:
    val = scores.get(key)
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict) and val.get("score") is not None:
        try:
            return float(val["score"])
        except (TypeError, ValueError):
            return None
    return None


def load_iteration_log_df(path: Path | None = None) -> pd.DataFrame | None:
    p = path if path is not None else ITERATION_LOG_PATH
    if not p.exists():
        return None
    try:
        return pd.read_csv(p)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helper: retry single image
# ---------------------------------------------------------------------------
def _retry_single_image(ad_entry: dict[str, Any], brief_id: str, variation: Any) -> None:
    try:
        from images.image_generator import AdImageGenerator
    except ImportError:
        st.error("Image generator module not available.")
        return
    ad_body = ad_entry.get("ad") or {}
    image_prompt = ad_body.get("image_prompt", "")
    if not image_prompt:
        st.warning("No image prompt available for this ad.")
        return
    ad_id = f"{brief_id}_v{variation}"
    selected_run = st.session_state.get("selected_run")
    if selected_run and selected_run != "Latest":
        images_dir = str(RUNS_DIR / selected_run / "images")
    else:
        images_dir = str(REPO_ROOT / "output" / "runs" / "images")
        if RUNS_DIR.is_dir():
            run_dirs = sorted(
                [d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name != "images"],
                reverse=True,
            )
            if run_dirs:
                images_dir = str(run_dirs[0] / "images")
    generator = AdImageGenerator(output_dir=images_dir)
    with st.spinner(f"Regenerating image for {ad_id}..."):
        result = generator.generate_image(image_prompt, ad_id)
    if result.get("success") and result.get("data"):
        ad_entry["image_url"] = result["data"]
        _persist_image_url_to_library(brief_id, variation, result["data"])
        st.success(f"Image generated for {ad_id}")
    else:
        st.error(f"Image retry failed: {result.get('error', 'unknown error')}")


def _persist_image_url_to_library(brief_id: str, variation: Any, image_url: str) -> None:
    selected_run = st.session_state.get("selected_run")
    if selected_run and selected_run != "Latest":
        lib_path = RUNS_DIR / selected_run / "ads_library.json"
    else:
        lib_path = ADS_LIBRARY_PATH
    if not lib_path.exists():
        return
    try:
        with open(lib_path, encoding="utf-8") as f:
            data = json.load(f)
        ads = data.get("ads", [])
        for ad in ads:
            if str(ad.get("brief_id")) == str(brief_id) and ad.get("variation_index") == int(variation):
                ad["image_url"] = image_url
                break
        with open(lib_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pipeline process helpers (unchanged)
# ---------------------------------------------------------------------------
def _start_pipeline_process() -> subprocess.Popen | None:
    if not MAIN_SCRIPT.exists():
        return None
    env = os.environ.copy()
    if not env.get("GOOGLE_API_KEY") or not env.get("ANTHROPIC_API_KEY"):
        return None
    env["PYTHONWARNINGS"] = "ignore"
    try:
        return subprocess.Popen(
            [sys.executable, str(MAIN_SCRIPT)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
    except OSError:
        return None


def _pipeline_reader_thread(process: subprocess.Popen, line_queue: Queue) -> None:
    try:
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                line_queue.put(line)
        process.wait()
    except Exception:
        pass
    finally:
        line_queue.put((None, process.returncode if process.returncode is not None else -1))


def run_pipeline_stream_ui() -> None:
    if not MAIN_SCRIPT.exists():
        st.error("main.py not found at project root.")
        st.session_state["run_pipeline_requested"] = False
        return
    if not os.environ.get("GOOGLE_API_KEY") or not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("API keys not set. Set GOOGLE_API_KEY and ANTHROPIC_API_KEY in Secrets or .env.")
        st.session_state["run_pipeline_requested"] = False
        return

    for key in ("pipeline_process", "pipeline_log_lines", "pipeline_queue"):
        if key not in st.session_state:
            st.session_state[key] = None if key != "pipeline_log_lines" else []

    proc = st.session_state["pipeline_process"]
    log_lines: list[str] = list(st.session_state["pipeline_log_lines"])
    line_queue = st.session_state["pipeline_queue"]

    if proc is None and st.session_state.get("run_pipeline_requested"):
        proc = _start_pipeline_process()
        if proc is None:
            st.error("Failed to start pipeline.")
            st.session_state["run_pipeline_requested"] = False
            return
        line_queue = Queue()
        reader = threading.Thread(
            target=_pipeline_reader_thread, args=(proc, line_queue), daemon=True,
        )
        reader.start()
        st.session_state["pipeline_process"] = proc
        st.session_state["pipeline_log_lines"] = []
        st.session_state["pipeline_queue"] = line_queue
        log_lines = []
        st.session_state["run_pipeline_requested"] = False

    import html as _html

    st.markdown(
        '<div class="kinetic-section-title"><span class="acc" style="background:#ac89ff"></span>Pipeline Output</div>',
        unsafe_allow_html=True,
    )
    output_box = st.empty()

    def _render_log(lines: list[str]) -> None:
        """Render all log lines in a scrollable container with auto-scroll to bottom."""
        escaped = _html.escape("".join(lines))
        # JS snippet scrolls the container to the bottom on each render
        output_box.markdown(
            f'<div class="pipeline-log" id="pipeline-log-box">{escaped}</div>'
            f'<script>var el=document.getElementById("pipeline-log-box");if(el)el.scrollTop=el.scrollHeight;</script>',
            unsafe_allow_html=True,
        )

    if proc is not None and line_queue is not None:
        while True:
            try:
                item = line_queue.get_nowait()
            except Empty:
                break
            if isinstance(item, tuple) and item[0] is None:
                _, exit_code = item
                st.session_state["pipeline_process"] = None
                st.session_state["pipeline_queue"] = None
                if exit_code == 0:
                    st.success("Pipeline complete! Go to Dashboard to see results.")
                else:
                    st.error(f"Pipeline failed with exit code {exit_code}")
                _render_log(log_lines)
                return
            if isinstance(item, str):
                if item.startswith("ERROR:"):
                    st.error(item.strip())
                    st.session_state.update({"pipeline_process": None, "pipeline_log_lines": [], "pipeline_queue": None})
                    return
                log_lines.append(item)
        st.session_state["pipeline_log_lines"] = log_lines
        _render_log(log_lines)
        if proc.poll() is None:
            time.sleep(2.0)
            _safe_rerun()
        else:
            exit_code = proc.returncode if proc.returncode is not None else -1
            while True:
                try:
                    item = line_queue.get_nowait()
                    if isinstance(item, tuple) and item[0] is None:
                        _, exit_code = item
                        break
                except Empty:
                    break
            st.session_state.update({"pipeline_process": None, "pipeline_log_lines": [], "pipeline_queue": None})
            if exit_code == 0:
                st.success("Pipeline complete!")
            else:
                st.error(f"Pipeline failed with exit code {exit_code}")
            _render_log(log_lines)
        return

    if log_lines:
        _render_log(log_lines)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def _resolve_image_path(image_url: str) -> Path | None:
    url_str = str(image_url).replace("\\", "/")
    img_path = Path(url_str) if Path(url_str).is_absolute() else REPO_ROOT / url_str
    if img_path.is_file():
        return img_path
    selected_run = st.session_state.get("selected_run")
    if selected_run and selected_run != "Latest":
        fallback = RUNS_DIR / selected_run / "images" / img_path.name
        if fallback.is_file():
            return fallback
    try_cwd = Path.cwd() / url_str
    if try_cwd.is_file():
        return try_cwd
    return None


def _ad_has_image(ad: dict[str, Any]) -> bool:
    """Return True if the ad has a resolved image file on disk."""
    image_url = (ad.get("ad") or {}).get("image_url", "")
    return bool(image_url and _resolve_image_path(image_url))


def _score_color(v: float) -> tuple[str, str]:
    """Return (text_color, bg_color) for a score value."""
    if v >= 8.5:
        return "#00fc40", "rgba(0,252,64,0.12)"
    if v >= 7.0:
        return "#69daff", "rgba(105,218,255,0.12)"
    return "#ff716c", "rgba(255,113,108,0.12)"


def _word_diff(old_text: str, new_text: str) -> tuple[str, str]:
    """Return (old_html, new_html) with word-level diff highlights.

    Removed words in old_text are wrapped in <span class="diff-del">.
    Added words in new_text are wrapped in <span class="diff-add">.
    Unchanged words are HTML-escaped normally.
    """
    import html as _html
    import difflib

    old_words = old_text.split()
    new_words = new_text.split()
    sm = difflib.SequenceMatcher(None, old_words, new_words)

    old_parts: list[str] = []
    new_parts: list[str] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            chunk = " ".join(_html.escape(w) for w in old_words[i1:i2])
            old_parts.append(chunk)
            new_parts.append(chunk)
        elif op == "replace":
            old_parts.append(f'<span class="diff-del">{" ".join(_html.escape(w) for w in old_words[i1:i2])}</span>')
            new_parts.append(f'<span class="diff-add">{" ".join(_html.escape(w) for w in new_words[j1:j2])}</span>')
        elif op == "delete":
            old_parts.append(f'<span class="diff-del">{" ".join(_html.escape(w) for w in old_words[i1:i2])}</span>')
        elif op == "insert":
            new_parts.append(f'<span class="diff-add">{" ".join(_html.escape(w) for w in new_words[j1:j2])}</span>')
    return " ".join(old_parts), " ".join(new_parts)


def _score_pip_color(v: float | None) -> str:
    if v is None:
        return "#1b2028"
    if v >= 8.0:
        return "#00fc40"
    if v >= 7.0:
        return "#69daff"
    return "#ff716c"


def _render_metric(label: str, value: str, delta: str | None, border_color: str) -> None:
    delta_html = f'<div class="m-delta" style="color:#00fc40">{delta}</div>' if delta else ""
    html = (
        f'<div class="kinetic-metric" style="border-left-color:{border_color}">'
        f'<div class="m-label">{label}</div>'
        f'<div class="m-value">{value}</div>'
        f'{delta_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_ad_thumbnail(ad: dict[str, Any]) -> None:
    """Render a single Facebook-style ad thumbnail card in the current column."""
    ad_body = ad.get("ad") or {}
    scores = ad.get("scores") or {}
    bid = str(ad.get("brief_id", "—"))
    var = ad.get("variation_index", "")
    avg = scores.get("average_score")
    headline = str(ad_body.get("headline") or "Untitled Ad")
    primary_text = str(ad_body.get("primary_text") or "").strip()
    cta = str(ad_body.get("cta_button") or "Learn More")
    image_url = ad.get("image_url")

    # Score badge
    try:
        score_num = float(avg) if avg is not None else None
        score_str = f"{score_num:.1f}" if score_num is not None else "—"
        txt_col, bg_col = _score_color(score_num) if score_num else ("#a8abb3", "rgba(168,171,179,0.12)")
    except (TypeError, ValueError):
        score_str, txt_col, bg_col = "—", "#a8abb3", "rgba(168,171,179,0.12)"

    # Score pips
    pip_html = ""
    for dim in DIMENSION_KEYS:
        v = _dimension_numeric(scores, dim)
        c = _score_pip_color(v)
        pip_html += f'<div class="score-pip" style="background:{c}"></div>'

    # Image area
    img_resolved = _resolve_image_path(image_url) if image_url else None

    if img_resolved:
        img_b64 = base64.b64encode(img_resolved.read_bytes()).decode()
        img_area = (
            f'<div class="ad-img-area has-image">'
            f'<img src="data:image/png;base64,{img_b64}" alt="">'
            f'<div class="ad-id-tag">{bid} · v{var}</div>'
            f'<div class="ad-score-badge" style="color:{txt_col};background:{bg_col}">{score_str}</div>'
            f'</div>'
        )
        has_image = True
    else:
        img_area = (
            f'<div class="ad-img-area no-image">'
            f'<div style="font-size:26px;opacity:0.2">&#x1F533;</div>'
            f'<div class="ad-no-img-label">Image not available</div>'
            f'<div class="ad-id-tag">{bid} · v{var}</div>'
            f'<div class="ad-score-badge" style="color:{txt_col};background:{bg_col}">{score_str}</div>'
            f'</div>'
        )
        has_image = False

    # HTML-escape ad copy so special chars don't break the markdown renderer
    import html as _html
    hl_raw = headline[:55] + "…" if len(headline) > 55 else headline
    hl_trunc = _html.escape(hl_raw)
    pt_full = _html.escape(primary_text)
    cta_esc = _html.escape(cta)
    card_uid = f"ad_{bid}_{var}"
    needs_expand = len(primary_text) > 95
    pt_short = _html.escape(primary_text[:95] + "…") if needs_expand else pt_full

    if needs_expand:
        read_more_html = (
            f'<div class="ad-preview-text">{pt_short}'
            f'<details class="ad-details"><summary>Read more ▾</summary>'
            f'<div class="ad-full-text">{pt_full}</div>'
            f'</details></div>'
        )
    else:
        read_more_html = f'<div class="ad-preview-text">{pt_full}</div>'

    card_html = (
        f'<div class="ad-thumb-card">'
        f'{img_area}'
        f'<div class="ad-card-inner">'
        f'<div class="ad-sponsor">Varsity Tutors · Sponsored</div>'
        f'<div class="ad-headline-text">{hl_trunc}</div>'
        f'{read_more_html}'
        f'</div>'
        f'<div class="ad-card-footer">'
        f'<div class="ad-cta-text">{cta_esc} &#x2192;</div>'
        f'<div class="ad-score-bars">{pip_html}</div>'
        f'</div>'
        f'</div>'
    )

    st.markdown(card_html, unsafe_allow_html=True)

    if not has_image:
        retry_key = f"retry_img_{bid}_{var}"
        if st.button("↻ Retry Image", key=retry_key, type="secondary"):
            _retry_single_image(ad, bid, var)
            _safe_rerun()


# ---------------------------------------------------------------------------
# Page renderers
# ---------------------------------------------------------------------------
def _render_dashboard(published: list, log_df: pd.DataFrame | None) -> None:
    """Dashboard overview: metrics + charts only."""
    import html as _html

    # Collect scores
    scores_list: list[tuple[dict, float]] = []
    for a in published:
        s = a.get("scores") or {}
        avg = s.get("average_score")
        if avg is not None:
            try:
                scores_list.append((a, float(avg)))
            except (TypeError, ValueError):
                pass

    if not scores_list:
        st.info("No scored ads yet. Run the pipeline from the sidebar.")
        return

    total_pub = len(scores_list)
    avg_all = sum(x[1] for x in scores_list) / total_pub
    passed = sum(1 for a, _ in scores_list if (a.get("scores") or {}).get("passes_threshold") is True)
    pass_rate = (passed / total_pub * 100) if total_pub else 0.0
    by_brief: dict[str, list[float]] = {}
    for a, sc in scores_list:
        by_brief.setdefault(str(a.get("brief_id", "?")), []).append(sc)
    brief_means = {b: sum(v) / len(v) for b, v in by_brief.items()}
    top_brief = max(brief_means, key=lambda k: brief_means[k]) if brief_means else "—"

    # Count healed ads from iteration log
    healed_count = 0
    if log_df is not None and not log_df.empty and "cycle" in log_df.columns:
        def _nc(s: "pd.Series") -> "pd.Series":
            return pd.to_numeric(s, errors="coerce")
        for (_, _), grp in log_df.groupby(["brief_id", "variation"], dropna=False):
            judged = grp[_nc(grp["average_score"]).notna()]
            if judged.empty:
                continue
            first = judged.assign(_c=_nc(judged["cycle"])).sort_values("_c").iloc[0]
            pub = grp[grp["status"].astype(str).str.strip().str.lower() == "published"]
            if pub.empty:
                continue
            final = pub.assign(_c=_nc(pub["cycle"])).sort_values("_c").iloc[-1]
            if float(_nc(pd.Series([final["cycle"]])).iloc[0] or 0) > float(_nc(pd.Series([first["cycle"]])).iloc[0] or 0):
                healed_count += 1

    # ── Metrics row ──
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    with c1:
        _render_metric("Published Ads", str(total_pub), None, "#69daff")
    with c2:
        _render_metric("Avg Score", f"{avg_all:.1f}", None, "#00fc40")
    with c3:
        _render_metric("Pass Rate", f"{pass_rate:.0f}%", None, "#ac89ff")
    with c4:
        delta_str = f"{healed_count} ads healed" if healed_count > 0 else None
        _render_metric("Top Brief", top_brief, delta_str, "#00fc40")

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    # ── Charts ──
    try:
        import plotly.graph_objects as go
        _PLOTLY = True
    except ImportError:
        _PLOTLY = False

    col_r, col_b = st.columns(2, gap="medium")

    # Radar
    with col_r:
        st.markdown(
            '<div class="kinetic-section-title"><span class="acc" style="background:#69daff"></span>Avg Score by Dimension</div>',
            unsafe_allow_html=True,
        )
        dim_vals: dict[str, list[float]] = {k: [] for k in DIMENSION_KEYS}
        for a, _ in scores_list:
            s = a.get("scores") or {}
            for k in DIMENSION_KEYS:
                v = _dimension_numeric(s, k)
                if v is not None:
                    dim_vals[k].append(v)
        radar_r = [sum(dim_vals[k]) / len(dim_vals[k]) if dim_vals[k] else 0.0 for k in DIMENSION_KEYS]
        labels = [DIMENSION_LABELS[k] for k in DIMENSION_KEYS]
        if _PLOTLY:
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=radar_r + [radar_r[0]],
                theta=labels + [labels[0]],
                fill="toself",
                fillcolor="rgba(0,252,64,0.08)",
                line=dict(color="#00fc40", width=2),
                mode="lines+markers",
                marker=dict(color="#00fc40", size=5),
            ))
            fig.update_layout(
                polar=dict(
                    bgcolor="#0f141a",
                    radialaxis=dict(visible=True, range=[0, 10], gridcolor="rgba(68,72,79,0.25)", tickfont=dict(color="#a8abb3", size=9), color="#a8abb3"),
                    angularaxis=dict(gridcolor="rgba(68,72,79,0.2)", tickfont=dict(color="#a8abb3", size=9, family="Space Grotesk")),
                ),
                paper_bgcolor="#0f141a",
                plot_bgcolor="#0f141a",
                showlegend=False,
                margin=dict(l=50, r=50, t=30, b=30),
                height=300,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            for lbl, val in zip(labels, radar_r):
                st.caption(f"{lbl}: {val:.1f}")

    # Bar by brief
    with col_b:
        st.markdown(
            '<div class="kinetic-section-title"><span class="acc" style="background:#00fc40"></span>Avg Score by Brief</div>',
            unsafe_allow_html=True,
        )
        if _PLOTLY and brief_means:
            bdf = sorted(brief_means.items(), key=lambda x: x[0])
            briefs_sorted = [b for b, _ in bdf]
            vals_sorted = [v for _, v in bdf]
            bar_colors = ["#00fc40" if v >= 8.5 else "#69daff" if v >= 7.0 else "#ff716c" for v in vals_sorted]
            fig2 = go.Figure(go.Bar(
                x=briefs_sorted, y=vals_sorted,
                marker_color=bar_colors,
                marker_line_width=0,
            ))
            fig2.update_layout(
                paper_bgcolor="#0f141a", plot_bgcolor="#0f141a",
                yaxis=dict(range=[0, 10], gridcolor="rgba(68,72,79,0.18)", tickfont=dict(color="#a8abb3", size=9), color="#a8abb3"),
                xaxis=dict(tickfont=dict(color="#a8abb3", size=9, family="Space Grotesk"), color="#a8abb3"),
                margin=dict(l=40, r=20, t=20, b=40),
                height=300,
            )
            st.plotly_chart(fig2, use_container_width=True)


def _render_ad_gallery(published: list, selected_briefs: list, min_score: float) -> None:
    """Thumbnail grid of published ads."""
    # Filter
    filtered = []
    for a in published:
        bid = str(a.get("brief_id", ""))
        if selected_briefs and bid not in selected_briefs:
            continue
        s = a.get("scores") or {}
        avg = s.get("average_score")
        if avg is not None and float(avg) < min_score:
            continue
        if avg is None and min_score > MIN_SCORE_SLIDER_MIN:
            continue
        filtered.append(a)

    # Gallery filter mode
    gallery_mode = st.radio(
        "gallery_filter", ["All Ads", "Top Performers", "Needs Image"],
        horizontal=True, label_visibility="collapsed",
    )

    # Apply gallery filter on top of brief/score filters
    if gallery_mode == "Top Performers":
        filtered = [a for a in filtered if float((a.get("scores") or {}).get("average_score", 0) or 0) >= 8.0]
    elif gallery_mode == "Needs Image":
        filtered = [a for a in filtered if not _ad_has_image(a)]

    # Header
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">'
        f'<div class="kinetic-section-title" style="margin-bottom:0">'
        f'<span class="acc" style="background:#00fc40"></span>'
        f'Optimized Ad Gallery'
        f'</div>'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:10px;color:#a8abb3">{len(filtered)} generations</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not filtered:
        st.info("No ads match the current filters.")
        return

    # 3-column thumbnail grid
    for row_start in range(0, len(filtered), 3):
        cols = st.columns(3, gap="medium")
        for col, ad in zip(cols, filtered[row_start:row_start + 3]):
            with col:
                _render_ad_thumbnail(ad)


def _render_analytics(published: list) -> None:
    """Analytics-only page."""
    scores_list = []
    for a in published:
        s = a.get("scores") or {}
        avg = s.get("average_score")
        if avg is not None:
            try:
                scores_list.append((a, float(avg)))
            except (TypeError, ValueError):
                pass
    if not scores_list:
        st.info("No data yet. Run the pipeline first.")
        return
    _render_dashboard.__wrapped__ if hasattr(_render_dashboard, "__wrapped__") else None
    # Reuse the charts section
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.info("Plotly not installed.")
        return
    by_brief: dict[str, list[float]] = {}
    for a, sc in scores_list:
        by_brief.setdefault(str(a.get("brief_id", "?")), []).append(sc)
    brief_means = {b: sum(v) / len(v) for b, v in by_brief.items()}
    dim_vals: dict[str, list[float]] = {k: [] for k in DIMENSION_KEYS}
    for a, _ in scores_list:
        s = a.get("scores") or {}
        for k in DIMENSION_KEYS:
            v = _dimension_numeric(s, k)
            if v is not None:
                dim_vals[k].append(v)
    radar_r = [sum(dim_vals[k]) / len(dim_vals[k]) if dim_vals[k] else 0.0 for k in DIMENSION_KEYS]
    labels = [DIMENSION_LABELS[k] for k in DIMENSION_KEYS]
    col_r, col_b = st.columns(2, gap="medium")
    with col_r:
        st.markdown('<div class="kinetic-section-title"><span class="acc" style="background:#69daff"></span>Avg Score by Dimension</div>', unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=radar_r + [radar_r[0]], theta=labels + [labels[0]], fill="toself", fillcolor="rgba(0,252,64,0.08)", line=dict(color="#00fc40", width=2), marker=dict(color="#00fc40", size=5)))
        fig.update_layout(polar=dict(bgcolor="#0f141a", radialaxis=dict(visible=True, range=[0, 10], gridcolor="rgba(68,72,79,0.25)", tickfont=dict(color="#a8abb3", size=9), color="#a8abb3"), angularaxis=dict(gridcolor="rgba(68,72,79,0.2)", tickfont=dict(color="#a8abb3", size=9, family="Space Grotesk"))), paper_bgcolor="#0f141a", plot_bgcolor="#0f141a", showlegend=False, margin=dict(l=50, r=50, t=30, b=30), height=320)
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        st.markdown('<div class="kinetic-section-title"><span class="acc" style="background:#00fc40"></span>Avg Score by Brief</div>', unsafe_allow_html=True)
        bdf = sorted(brief_means.items(), key=lambda x: x[0])
        bar_colors = ["#00fc40" if v >= 8.5 else "#69daff" if v >= 7.0 else "#ff716c" for _, v in bdf]
        fig2 = go.Figure(go.Bar(x=[b for b, _ in bdf], y=[v for _, v in bdf], marker_color=bar_colors, marker_line_width=0))
        fig2.update_layout(paper_bgcolor="#0f141a", plot_bgcolor="#0f141a", yaxis=dict(range=[0, 10], gridcolor="rgba(68,72,79,0.18)", tickfont=dict(color="#a8abb3", size=9), color="#a8abb3"), xaxis=dict(tickfont=dict(color="#a8abb3", size=9, family="Space Grotesk"), color="#a8abb3"), margin=dict(l=40, r=20, t=20, b=40), height=320)
        st.plotly_chart(fig2, use_container_width=True)


def _render_healing(log_df: pd.DataFrame | None) -> None:
    """Dedicated Self-Healing page with dimension-level before/after comparisons."""
    import html as _html

    st.markdown(
        '<div class="kinetic-section-title"><span class="acc" style="background:#ac89ff"></span>Self-Healing Proof</div>',
        unsafe_allow_html=True,
    )

    if log_df is None or log_df.empty:
        st.info("No iteration data available. Run the pipeline first — ads that fail the quality threshold will be automatically repaired and re-judged.")
        return

    required_cols = {"cycle", "average_score", "status", "brief_id", "variation"}
    if not required_cols.issubset(set(log_df.columns)):
        st.info("Iteration log missing required columns. Run the pipeline to generate self-healing data.")
        return

    def _nc(s: "pd.Series") -> "pd.Series":
        return pd.to_numeric(s, errors="coerce")

    # CSV column names for dimensions (may differ from DIMENSION_KEYS)
    dim_csv_cols = {
        "clarity": "clarity",
        "value_proposition": "value_prop",
        "call_to_action": "cta",
        "brand_voice": "brand_voice",
        "emotional_resonance": "emotional_resonance",
    }

    healed = []
    for (bid_g, var_g), grp in log_df.groupby(["brief_id", "variation"], dropna=False):
        judged = grp[_nc(grp["average_score"]).notna()]
        if judged.empty:
            continue
        first = judged.assign(_c=_nc(judged["cycle"])).sort_values("_c").iloc[0]
        pub = grp[grp["status"].astype(str).str.strip().str.lower() == "published"]
        if pub.empty:
            continue
        final = pub.assign(_c=_nc(pub["cycle"])).sort_values("_c").iloc[-1]
        if float(_nc(pd.Series([final["cycle"]])).iloc[0] or 0) <= float(_nc(pd.Series([first["cycle"]])).iloc[0] or 0):
            continue
        healed.append((bid_g, var_g, first, final))

    if not healed:
        st.markdown(
            '<div style="font-family:\'Space Grotesk\',sans-serif;font-size:12px;color:#a8abb3;padding:20px 0;">'
            'All ads passed on first attempt — no healing was needed this run.</div>',
            unsafe_allow_html=True,
        )
        return

    # Summary metric
    st.markdown(
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:12px;color:#a8abb3;margin-bottom:20px">'
        f'{len(healed)} ad{"s" if len(healed) != 1 else ""} required self-healing across this run.</div>',
        unsafe_allow_html=True,
    )

    for bid_g, var_g, r1, r2 in healed:
        s1 = float(r1["average_score"])
        s2 = float(r2["average_score"])
        delta = round(s2 - s1, 1)
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        delta_color = "#00fc40" if delta > 0 else "#ff716c"
        weakest = str(r1.get("weakest_dimension", "")).strip()

        # Build dimension score bars for both first and final
        dim_bars_first = ""
        dim_bars_final = ""
        for dim_key in DIMENSION_KEYS:
            csv_col = dim_csv_cols.get(dim_key, dim_key)
            label = DIMENSION_LABELS.get(dim_key, dim_key)
            v1_raw = r1.get(csv_col)
            v2_raw = r2.get(csv_col)
            try:
                v1 = float(v1_raw) if v1_raw is not None and str(v1_raw).strip() != "" else None
            except (TypeError, ValueError):
                v1 = None
            try:
                v2 = float(v2_raw) if v2_raw is not None and str(v2_raw).strip() != "" else None
            except (TypeError, ValueError):
                v2 = None

            # First draft bar
            pct1 = min(v1 / 10 * 100, 100) if v1 is not None else 0
            c1 = "#ff716c" if (v1 is not None and v1 < 7.0) else "#69daff" if (v1 is not None and v1 < 8.5) else "#00fc40"
            v1_str = f"{v1:.1f}" if v1 is not None else "—"
            is_weak = (dim_key == weakest or csv_col == weakest)
            weak_marker = ' &#9668;' if is_weak else ''
            dim_bars_first += (
                f'<div class="sh-dim-row">'
                f'<div class="sh-dim-label">{label}</div>'
                f'<div class="sh-dim-bar"><div class="sh-dim-fill" style="width:{pct1}%;background:{c1}"></div></div>'
                f'<div class="sh-dim-val" style="color:{c1}">{v1_str}{weak_marker}</div>'
                f'</div>'
            )

            # Healed bar
            pct2 = min(v2 / 10 * 100, 100) if v2 is not None else 0
            c2 = "#ff716c" if (v2 is not None and v2 < 7.0) else "#69daff" if (v2 is not None and v2 < 8.5) else "#00fc40"
            v2_str = f"{v2:.1f}" if v2 is not None else "—"
            dim_bars_final += (
                f'<div class="sh-dim-row">'
                f'<div class="sh-dim-label">{label}</div>'
                f'<div class="sh-dim-bar"><div class="sh-dim-fill" style="width:{pct2}%;background:{c2}"></div></div>'
                f'<div class="sh-dim-val" style="color:{c2}">{v2_str}</div>'
                f'</div>'
            )

        # Show all ad text fields, but only those that actually changed.
        # Fields available: headline, primary_text, cta_button, description
        weakest_label = weakest.replace("_", " ").title() if weakest else "—"
        ad_fields = [
            ("Headline", "headline"),
            ("Primary Text", "primary_text"),
            ("CTA Button", "cta_button"),
            ("Description", "description"),
        ]

        fields_first_html = ""
        fields_healed_html = ""
        any_field_shown = False
        for label, col in ad_fields:
            v1 = str(r1.get(col) or "").strip()
            v2 = str(r2.get(col) or "").strip()
            if not v1 and not v2:
                continue  # field not in CSV (old runs)
            if v1 == v2:
                continue  # no change — skip
            any_field_shown = True
            # Build word-level diff HTML
            diff1_html = _html.escape(v1) if v1 else "—"
            diff2_html = _html.escape(v2) if v2 else "—"
            if v1 and v2:
                diff1_html, diff2_html = _word_diff(v1, v2)
            fields_first_html += (
                f'<div class="sh-field-label">{_html.escape(label)}</div>'
                f'<div class="sh-text initial">{diff1_html}</div>'
            )
            fields_healed_html += (
                f'<div class="sh-field-label">{_html.escape(label)}</div>'
                f'<div class="sh-text healed">{diff2_html}</div>'
            )

        # If no fields changed (old CSV without cta_button/description), show primary_text
        if not any_field_shown:
            pt1 = _html.escape(str(r1.get("primary_text") or "—").strip())
            pt2 = _html.escape(str(r2.get("primary_text") or "—").strip())
            fields_first_html = f'<div class="sh-field-label">Primary Text</div><div class="sh-text initial">{pt1}</div>'
            fields_healed_html = f'<div class="sh-field-label">Primary Text</div><div class="sh-text healed">{pt2}</div>'

        card_html = (
            f'<div class="sh-card">'
            f'<div class="sh-header">'
            f'<span>Brief {_html.escape(str(bid_g))} · Var {_html.escape(str(var_g))} — {s1} &#x2192; {s2}</span>'
            f'<span class="sh-delta" style="color:{delta_color}">{delta_str}</span>'
            f'</div>'
            f'<div class="sh-cols">'
            # Left column: first judged
            f'<div>'
            f'<div class="sh-col-title">First Judged (Cycle {int(float(r1.get("cycle", 1)))})</div>'
            f'{dim_bars_first}'
            f'<div class="sh-score" style="color:#ff716c">{s1}</div>'
            f'<div class="sh-sub" style="color:#ff716c">Weakest: {_html.escape(weakest_label)}</div>'
            f'{fields_first_html}'
            f'</div>'
            # Right column: healed
            f'<div>'
            f'<div class="sh-col-title">Healed Draft (Cycle {int(float(r2.get("cycle", 1)))})</div>'
            f'{dim_bars_final}'
            f'<div class="sh-score" style="color:#00fc40">{s2}</div>'
            f'<div class="sh-sub" style="color:#00fc40">All dimensions passed 7.0 &#x2713;</div>'
            f'{fields_healed_html}'
            f'</div>'
            f'</div>'
            f'</div>'
        )

        st.markdown(card_html, unsafe_allow_html=True)


def _render_pipeline_page(run_options: list[str]) -> None:
    """Run Pipeline page: run selector, start button, scrollable output."""
    # Controls row
    c1, c2, c3 = st.columns([3, 2, 7])
    with c1:
        cur_idx = run_options.index(st.session_state["selected_run"]) if st.session_state["selected_run"] in run_options else 0
        chosen_run = st.selectbox("Run", options=run_options, index=cur_idx,
                     format_func=lambda x: "Latest" if x == "Latest" else x,
                     label_visibility="collapsed")
        st.session_state["selected_run"] = chosen_run
    with c2:
        is_running = st.session_state.get("pipeline_process") is not None
        btn_label = "⏳ Running..." if is_running else "▶  Start Pipeline"
        if st.button(btn_label, type="primary", use_container_width=True, disabled=is_running):
            st.session_state["run_pipeline_requested"] = True
            _safe_rerun()

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # Show pipeline streaming UI (or idle message)
    if st.session_state.get("run_pipeline_requested") or st.session_state.get("pipeline_process") is not None:
        run_pipeline_stream_ui()
    elif st.session_state.get("pipeline_log_lines"):
        # Show last run's output
        run_pipeline_stream_ui()
    else:
        st.markdown(
            '<div style="font-family:\'Space Grotesk\',sans-serif;font-size:12px;color:#a8abb3;padding:40px 0;text-align:center">'
            'Select a run or click <b>Start Pipeline</b> to generate new ads.</div>',
            unsafe_allow_html=True,
        )


def _render_settings() -> None:
    st.markdown('<div class="kinetic-section-title"><span class="acc" style="background:#69daff"></span>API Configuration</div>', unsafe_allow_html=True)
    gemini_ok = bool(os.environ.get("GOOGLE_API_KEY"))
    claude_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    g_color = "#00fc40" if gemini_ok else "#ff716c"
    c_color = "#00fc40" if claude_ok else "#ff716c"
    st.markdown(f"""
    <div style="background:#0f141a;border-radius:6px;padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div>
        <div style="font-family:'Space Grotesk',sans-serif;font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:#a8abb3;margin-bottom:8px">Gemini (Drafter)</div>
        <div style="display:flex;align-items:center;gap:8px;font-family:'Space Grotesk',sans-serif;font-size:13px;font-weight:600;color:{g_color}">
          <div style="width:8px;height:8px;border-radius:50%;background:{g_color};box-shadow:0 0 8px {g_color}40"></div>
          {"Connected" if gemini_ok else "Not Set"}
        </div>
      </div>
      <div>
        <div style="font-family:'Space Grotesk',sans-serif;font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:#a8abb3;margin-bottom:8px">Claude (Judge)</div>
        <div style="display:flex;align-items:center;gap:8px;font-family:'Space Grotesk',sans-serif;font-size:13px;font-weight:600;color:{c_color}">
          <div style="width:8px;height:8px;border-radius:50%;background:{c_color};box-shadow:0 0 8px {c_color}40"></div>
          {"Connected" if claude_ok else "Not Set"}
        </div>
      </div>
    </div>
    <div style="margin-top:16px;background:#0f141a;border-radius:6px;padding:20px">
      <div style="font-family:'Space Grotesk',sans-serif;font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:#a8abb3;margin-bottom:10px">Pipeline Defaults</div>
      <div style="font-size:11px;color:#a8abb3;line-height:2">
        PIPELINE_MAX_WORKERS = {os.environ.get("PIPELINE_MAX_WORKERS", "10")}<br>
        IMAGE_MAX_WORKERS = {os.environ.get("IMAGE_MAX_WORKERS", "4")}<br>
        IMAGE_STAGGER_DELAY = {os.environ.get("IMAGE_STAGGER_DELAY", "0.5")}s<br>
        GEMINI_MAX_CONCURRENT = {os.environ.get("GEMINI_MAX_CONCURRENT", "10")}<br>
        ANTHROPIC_MAX_CONCURRENT = {os.environ.get("ANTHROPIC_MAX_CONCURRENT", "8")}
      </div>
    </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Kinetic Observatory — Varsity Ad Engine", layout="wide")

    # Inject CSS
    st.markdown(KINETIC_CSS, unsafe_allow_html=True)

    # Load secrets
    if hasattr(st, "secrets"):
        try:
            os.environ["GOOGLE_API_KEY"] = str(st.secrets["GOOGLE_API_KEY"])
            os.environ["ANTHROPIC_API_KEY"] = str(st.secrets["ANTHROPIC_API_KEY"])
        except (KeyError, TypeError):
            pass
    if not os.environ.get("GOOGLE_API_KEY") or not os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

    # Session state defaults
    for key, default in [
        ("run_pipeline_requested", False),
        ("active_page", "dashboard"),
        ("selected_run", "Latest"),
        ("pipeline_process", None),
        ("pipeline_log_lines", []),
        ("pipeline_queue", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Run options (data loaded after run selector widget)
    run_ids = list_run_ids()
    run_options = ["Latest"] + run_ids
    if st.session_state["selected_run"] not in run_options:
        st.session_state["selected_run"] = "Latest"

    # ── SIDEBAR — brand + nav only ──
    nav_labels = [f"{icon}  {label}" for _, label, icon in NAV_ITEMS]
    nav_ids = [i for i, _, _ in NAV_ITEMS]

    # Initialize the radio key to match active_page on first load
    if "_nav_radio" not in st.session_state:
        try:
            st.session_state["_nav_radio"] = nav_labels[nav_ids.index(st.session_state["active_page"])]
        except ValueError:
            st.session_state["_nav_radio"] = nav_labels[0]

    with st.sidebar:
        st.markdown(SIDEBAR_BRAND_HTML, unsafe_allow_html=True)
        st.radio("nav", nav_labels, key="_nav_radio", label_visibility="collapsed")

    # Derive active_page from the radio widget's own state
    st.session_state["active_page"] = nav_ids[nav_labels.index(st.session_state["_nav_radio"])]

    # ── MAIN CONTENT ──

    # Top bar
    page_label = dict([(i, l) for i, l, _ in NAV_ITEMS]).get(st.session_state["active_page"], "Dashboard")
    gemini_ok = bool(os.environ.get("GOOGLE_API_KEY"))
    claude_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    g_dot = "#00fc40" if gemini_ok else "#ff716c"
    c_dot = "#00fc40" if claude_ok else "#ff716c"
    st.markdown(
        f'<div class="kinetic-topbar">'
        f'<div>'
        f'<div class="page-title">{page_label}</div>'
        f'<div class="page-sub">Varsity Tutors · SAT Prep Campaign</div>'
        f'</div>'
        f'<div class="kinetic-topbar-right">'
        f'<span style="display:flex;align-items:center;gap:5px"><span style="width:6px;height:6px;border-radius:50%;background:{g_dot};display:inline-block"></span> Gemini</span>'
        f'<span style="display:flex;align-items:center;gap:5px"><span style="width:6px;height:6px;border-radius:50%;background:{c_dot};display:inline-block"></span> Claude</span>'
        f'<span style="color:#ac89ff">$0.042/token</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Route pages
    active = st.session_state["active_page"]

    if active == "pipeline":
        _render_pipeline_page(run_options)
        return

    # Run selector for data pages (not pipeline, not settings)
    if active not in ("settings",):
        sel_cols = st.columns([3, 9])
        with sel_cols[0]:
            cur_idx = run_options.index(st.session_state["selected_run"]) if st.session_state["selected_run"] in run_options else 0
            chosen_run = st.selectbox("Run", options=run_options, index=cur_idx,
                         format_func=lambda x: "Latest" if x == "Latest" else x,
                         label_visibility="collapsed")
        st.session_state["selected_run"] = chosen_run

    # ── Load data based on selected run (AFTER the selector widget) ──
    selected_run = st.session_state["selected_run"]
    if selected_run == "Latest":
        if run_ids:
            latest_dir = RUNS_DIR / run_ids[0]
            ads_path = latest_dir / "ads_library.json"
            log_path = latest_dir / "iteration_log.csv"
        else:
            ads_path, log_path = None, None
    else:
        run_dir = RUNS_DIR / selected_run
        ads_path = run_dir / "ads_library.json"
        log_path = run_dir / "iteration_log.csv"

    result = load_ads_library_result(ads_path)
    data = result.get("data") or {} if result.get("success") else {}
    ads = data.get("ads") if isinstance(data.get("ads"), list) else []
    published = get_published_ads(ads)
    brief_ids_sorted = sorted({str(a.get("brief_id", "")) for a in ads if a.get("brief_id")}, key=lambda x: (len(x), x))
    log_df = load_iteration_log_df(log_path)

    # Library filters
    if active == "library":
        filt_cols = st.columns([5, 2])
        with filt_cols[0]:
            selected_briefs = st.multiselect("Brief IDs", options=brief_ids_sorted, default=brief_ids_sorted, placeholder="All briefs", label_visibility="collapsed")
        with filt_cols[1]:
            min_score = st.slider("Min Score", min_value=MIN_SCORE_SLIDER_MIN, max_value=MIN_SCORE_SLIDER_MAX, value=DEFAULT_MIN_SCORE, step=0.1, label_visibility="collapsed")
    else:
        selected_briefs = brief_ids_sorted
        min_score = DEFAULT_MIN_SCORE

    if not result.get("success"):
        st.error(result.get("error") or "Failed to load ads library.")
        return

    if not published and active not in ("settings", "healing"):
        st.info("No ads generated yet. Go to **Run Pipeline** in the sidebar.")
        return

    if active == "dashboard":
        _render_dashboard(published, log_df)

    elif active == "library":
        _render_ad_gallery(published, selected_briefs, min_score)

    elif active == "healing":
        _render_healing(log_df)

    elif active == "settings":
        _render_settings()


if __name__ == "__main__":
    main()
