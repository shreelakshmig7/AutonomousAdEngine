import sys
from pathlib import Path

# Ensure project root is on path when running as python3 scripts/smoke_pr3.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# test_failures.py — run: python3 test_failures.py
import json
from iterate.controller import run_brief
from evaluate.rubrics import AdBrief

with open("data/briefs.json") as f:
    briefs_data = json.load(f)

for brief_data in briefs_data["briefs"]:
    brief = AdBrief(**{k: v for k, v in brief_data.items() if v is not None})
    result = run_brief(brief, {}, {}, variation_index=0, total_variations=5)
    status = result["status"]
    error = result.get("error") or ""
    cycles = result["cycles_used"]
    log = result.get("iteration_log", [])
    last_scores = ""
    if log:
        last = log[-1]
        last_scores = f"clarity={last.get('clarity')} vp={last.get('value_proposition')} cta={last.get('call_to_action')} bv={last.get('brand_voice')} er={last.get('emotional_resonance')} avg={last.get('average_score')}"
    print(f"{brief.id} | {status} | cycles={cycles} | {error[:80]} | {last_scores}")