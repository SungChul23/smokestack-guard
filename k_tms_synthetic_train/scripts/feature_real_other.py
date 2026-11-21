'''
- feature_real_other: 실측 OTHER(단서 있음) 사건의 특징 분포를 생성기 범위와 비교
'''
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from synth_train import real_events

series = real_events.load_series(
    ROOT / "data" / "other_series.csv", "2026-10-30 00:00", "2026-11-12 23:30"
)

rows = []
for (item, fact, code), ratios in series.items():
    for ev in real_events.extract_events(ratios):
        if ev["shape"] == "OTHER" and ev["cue"]:
            m30 = ev["curve"][3]                      # curve[3] = 진입 30분 전
            rows.append({
                "item": item,
                "m30": None if m30 is None else m30 * 100,
                "peak": ev["peak"] * 100,
                "high_rows": ev["high_rows"],
                "entries": ev["entries"],
                "after": None if ev["after"] is None else ev["after"] * 100,
                "stack": f"{fact}{code}"
            })
df = pd.DataFrame(rows)

# 값을 구간 이름으로 바꾸는 함수들 (생성기 범위가 구간 경계)
def b_m30(v):
    if pd.isna(v): return "빈 칸"
    return "70 미만" if v < 70 else "70~89"

def b_peak(v):
    if v <= 99: return "90~99"
    return "99 초과~100 미만" if v < 100 else "100 이상"

def b_rows(n):
    return {1: "1칸", 2: "2칸", 3: "3칸"}.get(n, "4칸 이상")

def b_entries(n):
    return "1회" if n == 1 else ("2회" if n == 2 else "3회 이상")

def b_after(v):
    if pd.isna(v): return "없음"
    if v < 70: return "70 미만"
    return "70~89" if v < 90 else "90 이상"

# 성분별 건수와 비율(%)을 한 표로 출력
def show(col, bucket, title):
    t = (df.assign(b=df[col].map(bucket))
           .groupby(["b", "item"]).size().unstack("item").fillna(0).astype(int))
    pct = (t / t.sum() * 100).round(1).add_suffix("%")
    print(f"\n[{title}]")
    print(pd.concat([t, pct], axis=1))

print("단서 있는 OTHER 사건 수:", df.groupby("item").size().to_dict())
show("m30", b_m30, "직전 30분 값 (생성기 70~89)")
show("peak", b_peak, "최고값 (생성기 90~99)")
show("high_rows", b_rows, "90% 이상 칸 수 (생성기 1~2)")
show("entries", b_entries, "진입 횟수 (생성기 1)")
show("after", b_after, "진입 뒤 값 (생성기 70~89)")

# 생성기 범위를 모두 만족하는 사건의 비율
covered = (
    (df["m30"].map(b_m30) == "70~89")
    & (df["peak"].map(b_peak) == "90~99")
    & (df["high_rows"] <= 2)
    & (df["entries"] == 1)
    & (df["after"].map(b_after) == "70~89")
)
print("\n[생성기 범위를 전부 만족하는 비율]")
print(covered.groupby(df["item"]).mean().round(3))

# 조합(서명)별 건수 상위 10개
df["sig"] = (df["m30"].map(b_m30) + " | " + df["peak"].map(b_peak) + " | "
             + df["high_rows"].map(b_rows) + " | " + df["entries"].map(b_entries)
             + " | " + df["after"].map(b_after))
for item, g in df.groupby("item"):
    print(f"\n[{item} 상위 조합]  직전 | 최고값 | 칸 수 | 진입 | 진입 뒤")
    print(g["sig"].value_counts().head(10))

# 최고값 100 이상 사건이 얼마나 높은가
hi = df[df["peak"] >= 100]
print("\n[최고값 100 이상 사건의 최고값 분포]")
print(hi.groupby("item")["peak"].describe(percentiles=[.5, .9, .99]).round(1))

# 사건이 소수 굴뚝에 몰렸나 (굴뚝 이름은 출력하지 않고 건수만)
for item, g in df.groupby("item"):
    vc = g["stack"].value_counts()
    print(f"\n[{item}] 굴뚝 수 {len(vc)}, 상위 10개 굴뚝 비중 "
          f"{vc.head(10).sum() / len(g):.1%}, 최다 1개 {vc.iloc[0]}건")