"""
app.py
------
Streamlit Cloud entrypoint for Varsity Ad Engine.
Dashboard layout: sidebar (API status, Run Pipeline, brief multiselect, min score);
main area — stats metrics, Plotly charts (radar, bar by brief, line by cycle),
and ad browser with expanders, progress bars, and optional images.
Runs main.py as subprocess with streaming stdout. Secrets → os.environ.
Load helpers return {"success", "data", "error"} where applicable — no raise.
Author: AutonomousAdEngine. Project: Varsity Ad Engine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Streamlit Cloud: set env before any code that reads API keys (subprocess inherits)
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

# Paths relative to repo root
REPO_ROOT: Path = Path(__file__).resolve().parent
ADS_LIBRARY_PATH: Path = REPO_ROOT / "output" / "ads_library.json"
ITERATION_LOG_PATH: Path = REPO_ROOT / "output" / "iteration_log.csv"
MAIN_SCRIPT: Path = REPO_ROOT / "main.py"
DEFAULT_MIN_SCORE: float = 7.0
MIN_SCORE_SLIDER_MIN: float = 5.0
MIN_SCORE_SLIDER_MAX: float = 10.0

# Dimension keys in ads_library scores (nested dict with "score") — order for radar
DIMENSION_KEYS: list[str] = [
    "clarity",
    "value_proposition",
    "call_to_action",
    "brand_voice",
    "emotional_resonance",
]
DIMENSION_LABELS: dict[str, str] = {
    "clarity": "Clarity",
    "value_proposition": "Value prop",
    "call_to_action": "CTA",
    "brand_voice": "Brand voice",
    "emotional_resonance": "Emotion",
}


def load_ads_library_result() -> dict[str, Any]:
    """
    Load ads_library.json from disk; structured result only.

    Returns:
        {"success": bool, "data": dict, "error": str | None}
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
        return {"success": False, "data": {}, "error": f"Invalid JSON: {e}"}
    except OSError as e:
        return {"success": False, "data": {}, "error": f"Cannot read file: {e}"}


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


def _dimension_numeric(scores: dict[str, Any], key: str) -> float | None:
    """
    Extract numeric score for a dimension from scores dict.

    Args:
        scores: Ad scores dict (may nest score under dict).
        key: Dimension key e.g. clarity.

    Returns:
        Float 0–10 or None if missing.
    """
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


def stream_pipeline() -> Iterator[str]:
    """
    Run main.py as subprocess and yield each stdout/stderr line as it arrives.

    Yields:
        Lines from process, then "EXIT_CODE:<int>".
    """
    if not MAIN_SCRIPT.exists():
        yield "ERROR: main.py not found at project root\n"
        return
    env = os.environ.copy()
    if not env.get("GOOGLE_API_KEY") or not env.get("ANTHROPIC_API_KEY"):
        yield "ERROR: API keys not set\n"
        return
    try:
        process = subprocess.Popen(
            [sys.executable, str(MAIN_SCRIPT)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
    except OSError as e:
        yield f"ERROR: Failed to start pipeline: {e}\n"
        return
    if process.stdout is None:
        yield "ERROR: Pipeline stdout not available\n"
        return
    try:
        for line in iter(process.stdout.readline, ""):
            yield line
    finally:
        process.stdout.close()
        process.wait()
    yield f"EXIT_CODE:{process.returncode if process.returncode is not None else -1}"


def render_sidebar_api_status() -> None:
    """Show Gemini / Claude connection status from env."""
    st.subheader("API status")
    gemini_ok = bool(os.environ.get("GOOGLE_API_KEY"))
    claude_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    st.markdown(
        f"{'🟢' if gemini_ok else '🔴'} **Gemini** — {'connected' if gemini_ok else 'not set'}"
    )
    st.markdown(
        f"{'🟢' if claude_ok else '🔴'} **Claude** — {'connected' if claude_ok else 'not set'}"
    )


def run_pipeline_stream_ui() -> None:
    """
    Run pipeline and stream last 30 lines into placeholder; then rerun.
    Must be called from main flow (not inside sidebar) so log appears in main.
    """
    if not MAIN_SCRIPT.exists():
        st.error("main.py not found at project root.")
        return
    st.subheader("Pipeline output")
    output_box = st.empty()
    log_lines: list[str] = []
    for line in stream_pipeline():
        if line.startswith("ERROR:"):
            st.error(line.strip())
            st.session_state.pop("run_pipeline_requested", None)
            return
        if line.startswith("EXIT_CODE:"):
            code_str = line.split(":", 1)[1].strip()
            try:
                code = int(code_str)
            except ValueError:
                code = -1
            if code == 0:
                st.success("Pipeline complete!")
            else:
                st.error(f"Pipeline failed with exit code {code}")
            break
        log_lines.append(line)
        output_box.code("".join(log_lines[-30:]), language=None)
    st.session_state.pop("run_pipeline_requested", None)
    st.rerun()


def load_iteration_log_df() -> pd.DataFrame | None:
    """
    Load iteration_log.csv if present.

    Returns:
        DataFrame or None.
    """
    if not ITERATION_LOG_PATH.exists():
        return None
    try:
        return pd.read_csv(ITERATION_LOG_PATH)
    except Exception:
        return None


def main() -> None:
    """Configure page, sidebar, and main dashboard sections."""
    st.set_page_config(
        page_title="Varsity Ad Engine",
        layout="wide",
    )

    result = load_ads_library_result()
    data = result.get("data") or {} if result.get("success") else {}
    ads = data.get("ads") if isinstance(data.get("ads"), list) else []
    published = get_published_ads(ads)

    brief_ids_sorted = sorted(
        {str(a.get("brief_id", "")) for a in ads if a.get("brief_id")},
        key=lambda x: (len(x), x),
    )

    # --- Sidebar ---
    with st.sidebar:
        render_sidebar_api_status()
        st.divider()
        if st.button("Run Pipeline", type="primary", use_container_width=True):
            st.session_state["run_pipeline_requested"] = True
            st.rerun()
        st.divider()
        st.subheader("Filters")
        selected_briefs = st.multiselect(
            "Brief IDs",
            options=brief_ids_sorted,
            default=brief_ids_sorted,
            placeholder="All briefs",
        )
        min_score = st.slider(
            "Min score",
            min_value=MIN_SCORE_SLIDER_MIN,
            max_value=MIN_SCORE_SLIDER_MAX,
            value=DEFAULT_MIN_SCORE,
            step=0.1,
        )

    st.title("Ad Generation Dashboard")
    st.caption("Varsity Tutors • SAT Prep Campaign")

    if st.session_state.get("run_pipeline_requested"):
        run_pipeline_stream_ui()
        return

    if not result.get("success"):
        st.error(result.get("error") or "Failed to load ads library")
        return

    if not published:
        st.info("No ads generated yet. Run the pipeline from the sidebar.")
        return

    # Collect scores for metrics and charts
    scores_list: list[tuple[dict[str, Any], float]] = []
    for a in published:
        s = a.get("scores") or {}
        avg = s.get("average_score")
        if avg is not None:
            try:
                scores_list.append((a, float(avg)))
            except (TypeError, ValueError):
                pass

    if not scores_list:
        st.info("No scored ads yet.")
        return

    total_published = len(scores_list)
    avg_all = sum(x[1] for x in scores_list) / total_published

    # Pass rate: published with passes_threshold True vs total with flag
    passed = sum(
        1
        for a, _ in scores_list
        if (a.get("scores") or {}).get("passes_threshold") is True
    )
    pass_rate_pct = (passed / total_published * 100) if total_published else 0.0

    # Highest scoring brief_id by mean average_score
    by_brief: dict[str, list[float]] = {}
    for a, sc in scores_list:
        bid = str(a.get("brief_id", "?"))
        by_brief.setdefault(bid, []).append(sc)
    brief_means = {b: sum(v) / len(v) for b, v in by_brief.items()}
    top_brief = max(brief_means, key=lambda k: brief_means[k]) if brief_means else "—"

    # --- Section 1: Stats row ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Published ads", total_published)
    c2.metric("Avg score", f"{avg_all:.1f}")
    c3.metric("Pass rate", f"{pass_rate_pct:.0f}%")
    c4.metric("Top brief", top_brief, delta=f"avg {brief_means.get(top_brief, 0):.1f}" if top_brief != "—" else None)

    st.divider()

    # --- Section 2: Charts ---
    # Radar: average per dimension across all published ads
    dim_sums: dict[str, list[float]] = {k: [] for k in DIMENSION_KEYS}
    for a, _ in scores_list:
        s = a.get("scores") or {}
        for k in DIMENSION_KEYS:
            v = _dimension_numeric(s, k)
            if v is not None:
                dim_sums[k].append(v)
    radar_theta = [DIMENSION_LABELS[k] for k in DIMENSION_KEYS]
    radar_r = [
        sum(dim_sums[k]) / len(dim_sums[k]) if dim_sums[k] else 0.0
        for k in DIMENSION_KEYS
    ]
    # Close the polygon
    radar_theta_closed = radar_theta + [radar_theta[0]]
    radar_r_closed = radar_r + [radar_r[0]]

    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("Avg score by dimension")
        fig_radar = go.Figure()
        fig_radar.add_trace(
            go.Scatterpolar(
                r=radar_r_closed,
                theta=radar_theta_closed,
                fill="toself",
                name="Average",
            )
        )
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
            showlegend=False,
            margin=dict(l=40, r=40, t=40, b=40),
            height=400,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with col_chart2:
        st.subheader("Avg score by brief")
        brief_df = pd.DataFrame(
            {"brief_id": list(brief_means.keys()), "avg_score": list(brief_means.values())}
        )
        brief_df = brief_df.sort_values("brief_id")
        fig_bar = px.bar(
            brief_df,
            x="brief_id",
            y="avg_score",
            range_y=[0, 10],
        )
        fig_bar.update_layout(height=400, margin=dict(l=40, r=40, t=40, b=40))
        st.plotly_chart(fig_bar, use_container_width=True)

    # Line chart: average score per cycle from iteration_log.csv
    st.subheader("Quality improvement over retry cycles")
    log_df = load_iteration_log_df()
    if log_df is not None and not log_df.empty and "cycle" in log_df.columns and "average_score" in log_df.columns:
        cycle_df = (
            log_df.groupby("cycle", as_index=False)["average_score"]
            .mean()
            .dropna()
        )
        cycle_df = cycle_df[cycle_df["cycle"].isin([1, 2, 3])]
        if not cycle_df.empty:
            cycle_df["cycle_label"] = cycle_df["cycle"].apply(lambda c: f"Cycle {int(c)}")
            fig_line = px.line(
                cycle_df,
                x="cycle_label",
                y="average_score",
                markers=True,
                range_y=[0, 10],
            )
            fig_line.update_layout(height=350, margin=dict(l=40, r=40, t=40, b=40))
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("No cycle 1–3 data in iteration log.")
    else:
        st.info("Run the pipeline to generate iteration_log.csv for cycle trends.")

    st.divider()

    # --- Section 3: Ad browser ---
    # Filter by sidebar multiselect and min score
    filtered: list[dict[str, Any]] = []
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

    st.subheader(f"Browse ads — {len(filtered)} published")

    for idx, a in enumerate(filtered):
        ad_body = a.get("ad") or {}
        scores = a.get("scores") or {}
        headline = ad_body.get("headline", f"Ad {idx + 1}")
        bid = a.get("brief_id", "—")
        var = a.get("variation_index", "")
        avg = scores.get("average_score", "—")
        title = f"Brief {bid} · Var {var} — {avg} avg"
        with st.expander(title, expanded=False):
            st.markdown(f"**{headline}**")
            st.write(ad_body.get("primary_text", "—"))
            for key in DIMENSION_KEYS:
                label = DIMENSION_LABELS[key]
                v = _dimension_numeric(scores, key)
                if v is not None:
                    st.caption(f"{label}: {v:.1f}")
                    st.progress(min(1.0, max(0.0, v / 10.0)))
                else:
                    st.caption(f"{label}: —")
            image_url = a.get("image_url")
            if image_url:
                img_path = REPO_ROOT / str(image_url)
                if img_path.is_file():
                    st.image(str(img_path), use_container_width=True)
                else:
                    st.caption(f"Image path not found: {image_url}")


if __name__ == "__main__":
    main()
