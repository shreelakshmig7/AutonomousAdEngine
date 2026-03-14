# test_selfheal.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluate.judge import AdJudge
from evaluate.rubrics import AdCopy

judge = AdJudge()

# Same ad, evaluated twice
ad = AdCopy(
    primary_text="That knot in your stomach after seeing your junior's PSAT score? It's okay. We help juniors turn disappointing scores into results with 1-on-1 tutoring. Get a free diagnostic and be matched with a top 5% tutor in 24 hours. Our students average 200+ point SAT improvement.",
    headline="Turn PSAT Disappointment Into SAT Success",
    description="Expert 1-on-1 prep starts with a free diagnostic, matched in 24 hours.",
    cta_button="Start Free Assessment",
    image_prompt="UGC-style close-up photo of a crumpled SAT practice test on a kitchen table. A red pen circles the score of 1180. No text overlays."
)

r1 = judge.evaluate_ad(ad)
r2 = judge.evaluate_ad(ad)

print("Run 1 avg:", r1["data"].average_score)
print("Run 2 avg:", r2["data"].average_score)
print("Diff:", round(r2["data"].average_score - r1["data"].average_score, 2))