import json
import pandas as pd
from evaluate.rubrics import QUALITY_THRESHOLD

with open('output/ads_library.json') as f:
    data = json.load(f)

ads = data if isinstance(data, list) else data.get('ads', [])
scores = [ad['scores']['average_score'] for ad in ads]

print(f'Total ads: {len(ads)}')
print(f'All above threshold: {all(s >= QUALITY_THRESHOLD for s in scores)}')
print(f'Min score: {min(scores):.2f}')
print(f'Max score: {max(scores):.2f}')
print(f'Avg score: {sum(scores)/len(scores):.2f}')
print()

log = pd.read_csv('output/iteration_log.csv')
print(f'Log rows: {len(log)}')
print(f'Columns: {list(log.columns)}')
print()
print('Status counts:')
print(log.status.value_counts())
print()
print('Unresolvable by brief:')
print(log[log.status == \"unresolvable\"].brief_id.value_counts())