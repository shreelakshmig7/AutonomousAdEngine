# test_variations.py — run: python3 tests/test_variations.py (from repo root)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate.drafter import AdDrafter
from evaluate.rubrics import AdBrief

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

for i in range(5):
    result = drafter.draft_ad(
        brief=brief,
        competitive_context={},
        brand_guidelines={},
        variation_index=i,
        total_variations=5,
    )
    print(f"\n--- VAR {i} ---")
    print("SUCCESS:", result["success"])
    print("ERROR:", result["error"])
    if result["data"]:
        ad = result["data"]
        print("HEADLINE:", ad.headline)
        print("HOOK:", ad.primary_text[:120])
        print("IMAGE:", ad.image_prompt[:100])