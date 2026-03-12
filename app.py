"""
app.py
------
Streamlit Cloud entrypoint for Varsity Ad Engine.
Loads ads from output/ads_library.json, runs main.py as subprocess with
live stdout, and browses ads with brief_id and min-score filters.
Secrets: GOOGLE_API_KEY, ANTHROPIC_API_KEY via st.secrets → os.environ.
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
        os.environ["GOOGLE_API_KEY"] = st.secrets["GOOGLE_API_KEY"]
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, TypeError):
        pass  # Local run without secrets; pipeline button will fail until secrets set

import pandas as pd

# Paths relative to repo root (Streamlit runs from root)
REPO_ROOT: Path = Path(__file__).resolve().parent
ADS_LIBRARY_PATH: Path = REPO_ROOT / "output" / "ads_library.json"
MAIN_SCRIPT: Path = REPO_ROOT / "main.py"
DEFAULT_MIN_SCORE: float = 7.0


def load_ads_library() -> dict[str, Any]:
    """
    Load ads_library.json from disk.

    Returns:
        Parsed JSON dict with key "ads" or empty dict on missing/invalid file.
    """
    if not ADS_LIBRARY_PATH.exists():
        return {}
    try:
        with open(ADS_LIBRARY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


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
    data = load_ads_library()
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

    # Bar chart: one bar per ad (label by brief_id + variation)
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


def run_pipeline_subprocess() -> int:
    """
    Run python main.py as subprocess from repo root.

    Returns:
        Process exit code.
    """
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, str(MAIN_SCRIPT)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        bufsize=1,
    )
    log_placeholder = st.empty()
    lines: list[str] = []
    if proc.stdout:
        for line in proc.stdout:
            lines.append(line)
            log_placeholder.code("".join(lines[-500:]), language=None)
    proc.wait()
    return proc.returncode if proc.returncode is not None else -1


def render_run_pipeline() -> None:
    """Render section 2: button to run main.py with live stdout."""
    st.header("Run Pipeline")
    if not MAIN_SCRIPT.exists():
        st.error("main.py not found at project root.")
        return

    if st.button("Run Pipeline (Generate Ads)", type="primary"):
        with st.spinner("Running pipeline…"):
            code = run_pipeline_subprocess()
        if code == 0:
            st.success("Pipeline completed successfully.")
        else:
            st.error(f"Pipeline exited with code {code}.")
        st.rerun()


def render_browse_ads() -> None:
    """Render section 3: browse ads with sidebar filters."""
    st.header("Browse Ads")
    data = load_ads_library()
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
        with st.expander(
            f"{ad_body.get('headline', 'Ad')[:60]}…"
            if len(str(ad_body.get("headline", ""))) > 60
            else ad_body.get("headline", f"Ad {idx + 1}"),
            expanded=False,
        ):
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
