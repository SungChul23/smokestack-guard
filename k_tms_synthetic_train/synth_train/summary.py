'''
- summary: manifest를 (날짜 x 성분 x 모양)별로 집계해 보여준다 (E가 데이터를 고르기 전에 보는 요약)
'''
import json
from collections import defaultdict
from pathlib import Path

# {(날짜, 성분, 모양): {"episodes": 에피소드 수, "rows": 행 수}}
def summarize(manifest_dir) -> dict:
    table = defaultdict(lambda: {"episodes": 0, "rows": 0})
    for p in sorted(Path(manifest_dir).glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            key = (r["day"], r["item"], r["shape"])
            table[key]["episodes"] += 1
            table[key]["rows"] += r["rows"]
    return dict(table)

# 날짜별 합계와 전체 성분 x 모양 합계를 출력
def print_summary(table: dict) -> None:
    per_day, total = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for (day, item, shape), v in table.items():
        per_day[day][0] += v["episodes"]
        per_day[day][1] += v["rows"]
        total[(item, shape)][0] += v["episodes"]
        total[(item, shape)][1] += v["rows"]
    print("[날짜별] 에피소드 / 행")
    for day in sorted(per_day):
        print(f"  {day}: {per_day[day][0]} / {per_day[day][1]}")
    print("[성분 x 모양 합계] 에피소드 / 행")
    for (item, shape) in sorted(total):
        print(f"  {item} {shape}: {total[(item, shape)][0]} / {total[(item, shape)][1]}")