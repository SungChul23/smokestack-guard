'''
- quantile_ranges: 실측 사건에서 세부 유형별 특징의 분위수를 뽑아 생성 범위의 근거로 사용
'''
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from synth_train import real_events

# 학습 구간만 사용 (검증, 테스트용 기간과 겹치지 않게 설정)
series = real_events.load_series(
    ROOT / "data" / "other_series.csv", "2026-10-30 00:00", "2026-11-11 23:00"
)

def pct(v):
    return None if v is None else v * 100

rows = []
for (item, fact, code), ratios in series.items():
    for ev in real_events.extract_events(ratios):
        if not ev["cue"]:
            continue
        m120, m90, m60, m30 = (pct(v) for v in ev["curve"][:4])
        rows.append({
            "item": item, "detail": ev["detail"],
            "m120": m120, "m90": m90, "m60": m60, "m30": m30,
            "peak": ev["peak"] * 100, "high_rows": ev["high_rows"],
            "after": pct(ev["after"]),
        })

df = pd.DataFrame(rows)

QS = [0.05, 0.25, 0.5, 0.75, 0.95]
for (item, detail), g in df.groupby(["item", "detail"]):
    print(f"\n[{item} {detail}] n={len(g)}")
    print(g[["m120", "m90", "m60", "m30", "peak", "high_rows", "after"]]
          .quantile(QS).round(1).T)

# 남은 OTHER가 무엇으로 이뤄줬는지
oth = df[df["detail"] == "OTHER"].copy()

def why_other(r):
    m = [r["m120"], r["m90"], r["m60"], r["m30"]]
    if any(pd.isna(v) for v in m):
        return "빈 칸 있음"
    if r["m120"] >= 90 or r["m90"] >= 90:
        return "앞 사건 있음(재접촉형)"
    if r["m30"] - r["m120"] <= -8:
        return "하강형"
    return "그 밖"

oth["why"] = oth.apply(why_other, axis=1)
print("\n[남은 OTHER 구성]")
print(oth.groupby(["why", "item"]).size().unstack("item").fillna(0).astype(int))

# 다른 유형에 앞 사건(90% 이상)이 섞인 비율
df["prior_high"] = (df["m120"] >= 90) | (df["m90"] >= 90)
print("\n[유형별 앞 사건 섞임 건수]")
print(df.groupby(["detail", "item"])["prior_high"].sum().unstack("item").fillna(0).astype(int))