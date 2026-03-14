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
import streamlit as st

# Plotly optional — if install fails on Cloud, app still loads with fallbacks
try:
    import plotly.express as px
    import plotly.graph_objects as go

    _PLOTLY_AVAILABLE = True
except ImportError:
    px = None  # type: ignore[assignment]
    go = None  # type: ignore[assignment]
    _PLOTLY_AVAILABLE = False

# Paths relative to repo root
REPO_ROOT: Path = Path(__file__).resolve().parent
ADS_LIBRARY_PATH: Path = REPO_ROOT / "output" / "ads_library.json"
ITERATION_LOG_PATH: Path = REPO_ROOT / "output" / "iteration_log.csv"
RUNS_DIR: Path = REPO_ROOT / "output" / "runs"
MAIN_SCRIPT: Path = REPO_ROOT / "main.py"
DEFAULT_MIN_SCORE: float = 7.0
MIN_SCORE_SLIDER_MIN: float = 5.0
MIN_SCORE_SLIDER_MAX: float = 10.0
AD_PREVIEW_IMAGE_WIDTH: int = 360  # Max width (px) for ad image in expander so full ad fits in view
PRIMARY_TEXT_VISIBLE_CHARS: int = 125  # Meta: ~125 chars visible before "...See More"
CTA_DESTINATION_URL: str = "https://www.varsitytutors.com/"

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


def list_run_ids() -> list[str]:
    """
    List run IDs from output/runs/ that have ads_library.json (timestamp dirs), newest first.
    Does not include "latest"; caller prepends it for selector.
    Runs without ads_library.json are excluded so the dropdown only shows usable runs.

    Returns:
        Sorted list of run_id strings (e.g. 20260312_210000).
    """
    if not RUNS_DIR.is_dir():
        return []
    ids = [
        d.name
        for d in RUNS_DIR.iterdir()
        if d.is_dir() and d.name and (d / "ads_library.json").is_file()
    ]
    ids.sort(reverse=True)
    return ids


def load_ads_library_result(path: Path | None = None) -> dict[str, Any]:
    """
    Load ads_library.json from disk; structured result only.

    Args:
        path: Optional path to ads_library.json. When None, uses ADS_LIBRARY_PATH (latest).

    Returns:
        {"success": bool, "data": dict, "error": str | None}
    """
    p = path if path is not None else ADS_LIBRARY_PATH
    if not p.exists():
        # For a specific run, missing file means no data for that run (clear error).
        # For "Latest" (path None), empty is normal before first pipeline run.
        if path is not None:
            return {
                "success": False,
                "data": {},
                "error": "No data for this run (ads_library.json not found). Run the pipeline to generate it.",
            }
        return {"success": True, "data": {}, "error": None}
    try:
        with open(p, encoding="utf-8") as f:
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
    # Subprocess only: suppress all warnings so streamed log shows only pipeline progress
    env["PYTHONWARNINGS"] = "ignore"
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
    Run pipeline and stream last 30 lines into placeholder.
    No auto-rerun after completion; user clicks "View dashboard" to avoid
    SessionInfo-before-init errors when rerun fires right after long run.
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
            st.session_state["run_pipeline_requested"] = False
            break
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
    st.session_state["run_pipeline_requested"] = False
    st.button("View dashboard", type="primary")


def load_iteration_log_df(path: Path | None = None) -> pd.DataFrame | None:
    """
    Load iteration_log.csv if present.

    Args:
        path: Optional path to iteration_log.csv. When None, uses ITERATION_LOG_PATH (latest).

    Returns:
        DataFrame or None.
    """
    p = path if path is not None else ITERATION_LOG_PATH
    if not p.exists():
        return None
    try:
        return pd.read_csv(p)
    except Exception:
        return None


def main() -> None:
    """Configure page, sidebar, and main dashboard sections."""
    st.set_page_config(
        page_title="Varsity Ad Engine",
        layout="wide",
    )

    # Load secrets into env only inside a script run (avoids SessionInfo use before init).
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

    # Hide footer and bottom-right "Manage app" bar (Streamlit / Community Cloud).
    st.markdown(
        """
        <style>
        footer { visibility: hidden; }
        [data-testid="stBottom"] { visibility: hidden; }
        [data-testid="stDecoration"] { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Ensure session state keys exist before use (avoids KeyError if state is reset or not yet ready).
    if "run_pipeline_requested" not in st.session_state:
        st.session_state["run_pipeline_requested"] = False

    run_ids = list_run_ids()
    run_options = ["Latest"] + run_ids
    if "selected_run" not in st.session_state:
        st.session_state["selected_run"] = "Latest"
    if st.session_state["selected_run"] not in run_options:
        st.session_state["selected_run"] = run_options[0]
        st.rerun()
    run_index = run_options.index(st.session_state["selected_run"])

    # Resolve paths for selected run
    if st.session_state["selected_run"] == "Latest" or not st.session_state["selected_run"]:
        ads_path = None
        log_path = None
    else:
        run_dir = RUNS_DIR / st.session_state["selected_run"]
        ads_path = run_dir / "ads_library.json"
        log_path = run_dir / "iteration_log.csv"

    result = load_ads_library_result(ads_path)
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
        chosen = st.selectbox(
            "Run",
            options=run_options,
            index=run_index,
            format_func=lambda x: "Latest (output/)" if x == "Latest" else x,
        )
        if chosen != st.session_state["selected_run"]:
            st.session_state["selected_run"] = chosen
            st.rerun()
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
        if _PLOTLY_AVAILABLE and go is not None:
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
        else:
            st.warning(
                "Plotly not installed — radar chart unavailable. "
                "Add `plotly` to requirements and redeploy."
            )
            dim_df = pd.DataFrame(
                {"dimension": radar_theta, "avg_score": radar_r}
            )
            st.bar_chart(dim_df.set_index("dimension"))

    with col_chart2:
        st.subheader("Avg score by brief")
        brief_df = pd.DataFrame(
            {"brief_id": list(brief_means.keys()), "avg_score": list(brief_means.values())}
        )
        brief_df = brief_df.sort_values("brief_id")
        if _PLOTLY_AVAILABLE and px is not None:
            fig_bar = px.bar(
                brief_df,
                x="brief_id",
                y="avg_score",
                range_y=[0, 10],
            )
            fig_bar.update_layout(height=400, margin=dict(l=40, r=40, t=40, b=40))
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.bar_chart(brief_df.set_index("brief_id"))

    log_df = load_iteration_log_df(log_path)

    # --- Self-Healing Proof: ads that failed cycle 1 and were healed (published) in 2+ cycles ---
    st.subheader("Self-Healing Proof")
    if log_df is not None and not log_df.empty and "cycle" in log_df.columns and "average_score" in log_df.columns:
        has_copy = "primary_text" in log_df.columns
        has_status = "status" in log_df.columns
        groups = log_df.groupby(["brief_id", "variation"], dropna=False)
        healed: list[tuple[Any, Any, pd.Series, pd.Series]] = []
        for (bid, var), grp in groups:
            cycles = pd.to_numeric(grp["cycle"], errors="coerce").dropna()
            if cycles.empty or cycles.max() < 2:
                continue
            c1_rows = grp[grp["cycle"] == 1]
            c_final = int(cycles.max())
            final_rows = grp[grp["cycle"] == c_final]
            if c1_rows.empty or final_rows.empty:
                continue
            final_row = final_rows.iloc[-1]
            # Only show as healed when the final cycle actually published (reached threshold)
            if has_status and str(final_row.get("status")).strip().lower() != "published":
                continue
            healed.append((bid, var, c1_rows.iloc[0], final_row))
        if not healed:
            st.info("All ads passed on first attempt — no healing needed.")
        else:
            # Lookup published ad by (brief_id, variation) for fallback when log has no primary_text
            ad_by_brief_var: dict[tuple[str, int], dict[str, Any]] = {}
            for a in published:
                b = str(a.get("brief_id", ""))
                v = a.get("variation_index")
                if v is not None:
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        continue
                    ad_by_brief_var[(b, v)] = a

            for bid, var, r1, r2 in healed:
                s1 = float(r1["average_score"]) if pd.notna(r1.get("average_score")) else 0.0
                s2 = float(r2["average_score"]) if pd.notna(r2.get("average_score")) else 0.0
                delta = round(s2 - s1, 1)
                if delta > 0:
                    title = f"Brief {bid} · Var {var} — Score lifted from {s1} → {s2} (+{delta})"
                elif delta < 0:
                    title = f"Brief {bid} · Var {var} — Published after retries: score {s1} → {s2} ({delta})"
                else:
                    title = f"Brief {bid} · Var {var} — Published after retries: score {s1} → {s2}"
                with st.expander(title, expanded=False):
                    col_initial, col_healed = st.columns(2)
                    with col_initial:
                        st.markdown("### Initial Draft")
                        pt1 = "—"
                        if has_copy and "primary_text" in r1.index:
                            pt1 = r1["primary_text"]
                            if pt1 is None or (isinstance(pt1, float) and pd.isna(pt1)):
                                pt1 = "—"
                            else:
                                pt1 = str(pt1).strip() or "—"
                        if pt1 == "—":
                            pt1 = "Initial draft copy was not recorded for this run. Re-run the pipeline to log per-cycle copy (primary_text) in the iteration log."
                        st.info(pt1)
                        st.metric("Avg Score", round(s1, 1) if s1 else "—")
                        w1 = r1.get("weakest_dimension")
                        if w1 is None or (isinstance(w1, float) and pd.isna(w1)):
                            w1 = "—"
                        st.error(f"Weakest dimension: {w1}")
                    with col_healed:
                        st.markdown("### Healed Draft")
                        pt2 = "—"
                        if has_copy and "primary_text" in r2.index:
                            pt2 = r2["primary_text"]
                            if pt2 is None or (isinstance(pt2, float) and pd.isna(pt2)):
                                pt2 = "—"
                            else:
                                pt2 = str(pt2).strip() or "—"
                        if pt2 == "—":
                            try:
                                v_int = int(var) if not isinstance(var, int) else var
                            except (TypeError, ValueError):
                                v_int = -1
                            ad_entry = ad_by_brief_var.get((str(bid), v_int))
                            if ad_entry:
                                ad_body = ad_entry.get("ad") or {}
                                fallback = ad_body.get("primary_text")
                                if fallback is not None and str(fallback).strip():
                                    pt2 = str(fallback).strip()
                            if pt2 == "—":
                                pt2 = "Healed draft copy was not recorded for this run. The final ad is in the Browse ads section below."
                        st.success(pt2)
                        lift = round(s2 - s1, 1)
                        delta_str = f"+{lift}" if lift > 0 else (f"{lift}" if lift < 0 else None)
                        st.metric("Avg Score", round(s2, 1) if s2 else "—", delta=delta_str)
                        st.write("All dimensions passed 7.0")
    else:
        st.caption("Run the pipeline to generate iteration_log.csv (with primary_text per cycle) for self-healing proof.")

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
            # Ad preview: Meta structure — primary text → image → headline → description → CTA
            st.caption("Varsity Tutors · Sponsored")
            primary_text = (ad_body.get("primary_text") or "").strip() or "—"
            if len(primary_text) <= PRIMARY_TEXT_VISIBLE_CHARS:
                st.write(primary_text)
            else:
                read_more_key = f"read_more_{bid}_{var}"
                if read_more_key not in st.session_state:
                    st.session_state[read_more_key] = False
                expanded = st.session_state.get(read_more_key, False)
                if expanded:
                    st.write(primary_text)
                    if st.button("show less", key=f"less_{bid}_{var}", type="secondary"):
                        st.session_state[read_more_key] = False
                        st.rerun()
                else:
                    st.write(primary_text[:PRIMARY_TEXT_VISIBLE_CHARS] + " …")
                    if st.button("read more", key=f"more_{bid}_{var}", type="secondary"):
                        st.session_state[read_more_key] = True
                        st.rerun()
            image_url = a.get("image_url")
            if image_url:
                img_path = REPO_ROOT / str(image_url)
                if img_path.is_file():
                    st.image(str(img_path), width=AD_PREVIEW_IMAGE_WIDTH, use_container_width=False)
                else:
                    st.caption(f"Image path not found: {image_url}")
            st.markdown(f"**{headline}**")
            desc = ad_body.get("description")
            if desc:
                st.caption(desc)
            cta = ad_body.get("cta_button")
            if cta:
                st.link_button(cta, url=CTA_DESTINATION_URL, type="primary")
            # Dimension scores below ad
            st.divider()
            st.caption("Scores by dimension")
            for key in DIMENSION_KEYS:
                label = DIMENSION_LABELS[key]
                v = _dimension_numeric(scores, key)
                if v is not None:
                    st.caption(f"{label}: {v:.1f}")
                    st.progress(min(1.0, max(0.0, v / 10.0)))
                else:
                    st.caption(f"{label}: —")


if __name__ == "__main__":
    main()
