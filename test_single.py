# test_single.py — drop in project root, run: python3 test_single.py
from generate.drafter import AdDrafter
from evaluate.rubrics import AdBrief
import json

drafter = AdDrafter()

brief = AdBrief(
    id="brief_001",
    audience="Parents of 11th graders in the Southeast (GA, NC, SC, FL) with household income $75K–$150K, actively searching 'SAT prep' and 'college admissions' in the last 30 days",
    product="SAT 1-on-1 tutoring with free diagnostic assessment; matched with a tutor in 24 hours based on exact weak areas",
    goal="conversion",
    tone="empathetic and urgent",
    hook_type="fear",
    difficulty="medium",
)

result = drafter.draft_ad(
    brief=brief,
    competitive_context={},
    brand_guidelines={},
    variation_index=0,
    total_variations=5,
)

print("SUCCESS:", result["success"])
print("MODEL:", result["model_used"])
print("ERROR:", result["error"])
if result["data"]:
    print("AD:", result["data"].model_dump_json(indent=2))