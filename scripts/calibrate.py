from evaluate.judge import AdJudge
from evaluate.rubrics import GOLD_ANCHOR, POOR_ANCHOR, AdCopy

# Initialize the Judge
judge = AdJudge()

print("--- Testing GOLD Anchor ---")
gold_ad = AdCopy.model_validate(GOLD_ANCHOR)
gold_result = judge.evaluate_ad(gold_ad)
print("--------------------------------")
print(gold_result)
print("--------------------------------")
if not gold_result["success"]:
    print(f"Error: {gold_result['error']}")
else:
    gold_report = gold_result["data"]
    print(f"Gold Average Score: {gold_report.average_score}")
    print(f"Passes Threshold: {gold_report.passes_threshold}")
# EXPECTED: >= 8.0 and True

print("\n--- Testing POOR Anchor ---")
poor_ad = AdCopy.model_validate(POOR_ANCHOR)
poor_result = judge.evaluate_ad(poor_ad)
if not poor_result["success"]:
    print(f"Error: {poor_result['error']}")
else:
    poor_report = poor_result["data"]
    print(f"Poor Average Score: {poor_report.average_score}")
    print(f"Passes Threshold: {poor_report.passes_threshold}")
    print(f"Weakest Dimension: {poor_report.weakest_dimension}")
# EXPECTED: <= 4.0 and False