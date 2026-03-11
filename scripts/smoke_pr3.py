"""Manual smoke: one brief through draft → judge. Run from repo root or any directory."""
import sys
from pathlib import Path

# Ensure project root is on path when running as python3 scripts/smoke_pr3.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.loaders import load_briefs, load_competitive_context, load_brand_guidelines
from generate.drafter import AdDrafter
from evaluate.judge import AdJudge

briefs = load_briefs()
context = load_competitive_context()
guidelines = load_brand_guidelines()

brief = briefs[0]
drafter = AdDrafter()
judge = AdJudge()

draft_result = drafter.draft_ad(brief, context, guidelines)
print("=== DRAFT ===")
print("success:", draft_result["success"])
if draft_result["data"]:
    print(draft_result["data"].model_dump_json(indent=2))
print("model_used:", draft_result["model_used"])

if draft_result["success"] and draft_result["data"]:
    eval_result = judge.evaluate_ad(draft_result["data"])
    print("\n=== EVALUATION ===")
    print("success:", eval_result["success"])
    if eval_result.get("data"):
        d = eval_result["data"]
        print("average_score:", d.average_score)
        print("passes_threshold:", d.passes_threshold)
        print("weakest_dimension:", d.weakest_dimension)