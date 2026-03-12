"""
app.py
------
Streamlit Cloud entrypoint for Varsity Ad Engine.
Loads ads from output/ads_library.json, runs main.py as subprocess,
and browses ads with brief_id and min-score filters.
Secrets: GOOGLE_API_KEY, ANTHROPIC_API_KEY via st.secrets → os.environ.
All pipeline/load helpers return {"success", "data", "error"} — no raise to caller.
Author: AutonomousAdEngine. Project: Varsity Ad Engine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# Streamlit Cloud: set env before any code that reads API keys (subprocess inherits)
if hasattr(st, "secrets"):
    try:
        os.environ["GOOGLE_API_KEY"] = str(st.secrets["GOOGLE_API_KEY"])
        os.environ["ANTHROPIC_API_KEY"] = str(st.secrets["ANTHROPIC_API_KEY"])
    except (KeyError, TypeError):
        pass  # Local run without secrets; pipeline returns structured error

import pandas as pd

# Paths relative to repo root (Streamlit runs from root)
REPO_ROOT: Path = Path(__file__).resolve().parent
ADS_LIBRARY_PATH: Path = REPO_ROOT / "output" / "ads_library.json"
MAIN_SCRIPT: Path = REPO_ROOT / "main.py"
DEFAULT_MIN_SCORE: float = 7.0
PIPELINE_TIMEOUT_SEC: int = 3600


def load_ads_library_result() -> dict[str, Any]:
    """
    Load ads_library.json from disk; structured result only.

    Returns:
        {"success": bool, "data": dict, "error": str | None}
        data is parsed JSON or {} when file missing (success True, empty ads).
    """
    if not ADS_LIBRARY_PATH.exists():
        return {"success": True, "data": {}, "error": None}
    try:
        with open(ADS_LIBRARY_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {
                "success": False,
                "data": {},
                "error": "ads_library.json root must be an object",
            }
        return {"success": True, "data": raw, "error": None}
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "data": {},
            "error": f"Invalid JSON: {e}",
        }
    except OSError as e:
        return {
            "success": False,
            "data": {},
            "error": f"Cannot read file: {e}",
        }


def get_published_ads(ads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return ads with status published, or all ads if no status field.

    Args:
        ads: Raw ad entries from ads_library.

    Returns:
        Filtered list of ad dicts.
    """
    if not ads:
        return []
    published = [a for a in ads if a.get("status") == "published"]
    return published if published else ads


def render_stats_dashboard() -> None:
    """Render section 1: stats and bar chart from ads_library.json."""
    st.header("Stats Dashboard")
    result = load_ads_library_result()
    if not result.get("success"):
        st.error(result.get("error") or "Failed to load ads library")
        return
    data = result.get("data") or {}
    ads = data.get("ads") if isinstance(data.get("ads"), list) else []

    if not ads:
        st.info("No ads generated yet")
        return

    published = get_published_ads(ads)
    scores = []
    for a in published:
        s = a.get("scores") or {}
        avg = s.get("average_score")
        if avg is not None:
            scores.append((a, float(avg)))

    if not scores:
        st.info("No ads generated yet")
        return

    total = len(published)
    avg_all = sum(x[1] for x in scores) / len(scores)
    best = max(scores, key=lambda x: x[1])
    worst = min(scores, key=lambda x: x[1])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total published ads", total)
    c2.metric("Average score", f"{avg_all:.2f}")
    c3.metric("Highest scoring ad", f"{best[1]:.2f}")
    c4.metric("Lowest scoring ad", f"{worst[1]:.2f}")

    labels = []
    values = []
    for a, sc in scores:
        bid = a.get("brief_id", "?")
        var = a.get("variation_index", "")
        labels.append(f"{bid} v{var}")
        values.append(sc)
    chart_df = pd.DataFrame({"score": values}, index=labels)
    st.subheader("Scores across all ads")
    st.bar_chart(chart_df)


def run_pipeline_subprocess_result() -> dict[str, Any]:
    """
    Run python main.py as subprocess from repo root; structured result only.

    Returns:
        {"success": bool, "data": {"stdout": str, "exit_code": int} | None, "error": str | None}
    """
    if not MAIN_SCRIPT.exists():
        return {
            "success": False,
            "data": None,
            "error": "main.py not found at project root",
        }
    env = os.environ.copy()
    if not env.get("GOOGLE_API_KEY") or not env.get("ANTHROPIC_API_KEY"):
        return {
            "success": False,
            "data": None,
            "error": "GOOGLE_API_KEY and ANTHROPIC_API_KEY must be set (secrets or .env)",
        }
    try:
        completed = subprocess.run(
            [sys.executable, str(MAIN_SCRIPT)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=PIPELINE_TIMEOUT_SEC,
            env=env,
        )
        stdout = (completed.stdout or "") + (
            ("\n--- stderr ---\n" + completed.stderr) if completed.stderr else ""
        )
        exit_code = completed.returncode if completed.returncode is not None else -1
        return {
            "success": exit_code == 0,
            "data": {"stdout": stdout, "exit_code": exit_code},
            "error": None if exit_code == 0 else f"Pipeline exited with code {exit_code}",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "data": None,
            "error": f"Pipeline timed out after {PIPELINE_TIMEOUT_SEC}s",
        }
    except OSError as e:
        return {
            "success": False,
            "data": None,
            "error": f"Failed to start pipeline: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": f"Pipeline error: {e}",
        }


def render_run_pipeline() -> None:
    """Render section 2: button to run main.py; output shown after completion."""
    st.header("Run Pipeline")
    if not MAIN_SCRIPT.exists():
        st.error("main.py not found at project root.")
        return

    if st.button("Run Pipeline (Generate Ads)", type="primary"):
        with st.spinner("Running pipeline…"):
            result = run_pipeline_subprocess_result()
        if result.get("data") and result["data"].get("stdout"):
            st.code(result["data"]["stdout"][-20000:], language=None)
        if result.get("success"):
            st.success("Pipeline completed successfully.")
        else:
            st.error(result.get("error") or "Pipeline failed.")
        st.rerun()


def render_browse_ads() -> None:
    """Render section 3: browse ads with sidebar filters."""
    st.header("Browse Ads")
    result = load_ads_library_result()
    if not result.get("success"):
        st.error(result.get("error") or "Failed to load ads library")
        return
    data = result.get("data") or {}
    ads = data.get("ads") if isinstance(data.get("ads"), list) else []

    if not ads:
        st.info("No ads generated yet")
        return

    brief_ids = sorted({str(a.get("brief_id", "")) for a in ads if a.get("brief_id")})
    with st.sidebar:
        st.subheader("Filters")
        brief_filter = st.selectbox(
            "Filter by brief_id",
            options=["(all)"] + brief_ids,
            index=0,
        )
        min_score = st.slider(
            "Min average score",
            min_value=0.0,
            max_value=10.0,
            value=DEFAULT_MIN_SCORE,
            step=0.1,
        )

    filtered: list[dict[str, Any]] = []
    for a in ads:
        if brief_filter != "(all)" and a.get("brief_id") != brief_filter:
            continue
        s = a.get("scores") or {}
        avg = s.get("average_score")
        if avg is not None and float(avg) < min_score:
            continue
        if avg is None and min_score > 0:
            continue
        filtered.append(a)

    st.caption(f"Showing {len(filtered)} ad(s)")

    for idx, a in enumerate(filtered):
        ad_body = a.get("ad") or {}
        scores = a.get("scores") or {}
        headline = ad_body.get("headline", f"Ad {idx + 1}")
        title = headline if len(str(headline)) <= 60 else f"{str(headline)[:60]}…"
        with st.expander(title, expanded=False):
            st.write("**brief_id:**", a.get("brief_id", "—"))
            st.write("**Headline:**", ad_body.get("headline", "—"))
            st.write("**Primary text:**", ad_body.get("primary_text", "—"))
            st.write("**Scores:**")
            for k, v in scores.items():
                if k != "average_score":
                    st.write(f"- {k}: {v}")
            st.write(f"- **average_score:** {scores.get('average_score', '—')}")


def main() -> None:
    """Configure page and render all sections."""
    st.set_page_config(
        page_title="Varsity Ad Engine",
        layout="wide",
    )
    st.title("Varsity Ad Engine")

    render_stats_dashboard()
    st.divider()
    render_run_pipeline()
    st.divider()
    render_browse_ads()


if __name__ == "__main__":
    main()
