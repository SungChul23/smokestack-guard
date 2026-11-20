'''
- lead_in_real_other: 실측 OTHER(단서 있음) 사건의 진입 전 곡선 유형을 나눠 비율을 봄
'''
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from synth_train import real_events

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

series = real_events.load_series(
    ROOT / "data" / "other_series.csv", "2026-10-30 00:00", "2026-11-12 23:30"
)

rows = []
for (item, fact, code), ratios in series.items():
    for ev in real_events.extract_events(ratios):
        if ev["shape"] == "OTHER" and ev["cue"]:
            # 진입 전 4칸 + 진입 칸, 단위 %, 빈 칸은 nan
            c = [np.nan if v is None else v * 100 for v in ev["curve"][:5]]
            rows.append({"item": item, "curve": c})
df = pd.DataFrame(rows)

# 진입 전 곡선 유형 (기준값 8은 탐색용 임의값)
def lead_type(c):
    lead = c[:4]                                    # -120, -90, -60, -30분
    valid = [v for v in lead if not np.isnan(v)]
    if any(v >= 90 for v in valid):
        return "앞 사건 섞임"                         # 앞 사건 값이 들어옴
    if len(valid) < 3:
        return "값 부족"
    spread = max(valid) - min(valid)                 # 4칸 안의 변화폭
    change = valid[-1] - valid[0]                    # 처음 → 마지막 변화
    if spread < 8:
        return "평탄"
    if change >= 8:
        return "상승"
    if change <= -8:
        return "하강"
    return "진동"

df["type"] = df["curve"].map(lead_type)

# 유형별 건수와 비율
t = df.groupby(["type", "item"]).size().unstack("item").fillna(0).astype(int)
print(pd.concat([t, (t / t.sum() * 100).round(1).add_suffix("%")], axis=1))

# 유형별 곡선: 중앙값과 25~75% 띠
x = [-120, -90, -60, -30, 0]
types = [k for k in ["평탄", "상승", "하강", "진동", "앞 사건 섞임", "값 부족"]
         if k in set(df["type"])]
fig, axes = plt.subplots(2, 3, figsize=(14, 7), sharey=True)
for ax, k in zip(axes.flat, types):
    arr = np.array(df[(df["type"] == k) & (df["item"] == "NOX")]["curve"].tolist())
    if len(arr) == 0:
        continue
    q1, q2, q3 = np.nanpercentile(arr, [25, 50, 75], axis=0)
    ax.fill_between(x, q1, q3, alpha=0.3)
    ax.plot(x, q2, color="red", marker="o")
    ax.axhline(90, color="gray", ls="--")
    ax.set_title(f"NOX {k} n={len(arr)}")
    ax.set_ylim(30, 110)
fig.tight_layout()
fig.savefig(ROOT / "data" / "other_lead_types.png", dpi=110)
print("저장: data/other_lead_types.png")

# 상승 유형이 GRADUAL 조건에서 어느 항목에 걸렸는지
up = df[df["type"] == "상승"].copy()

def why(c):
    m120, m90, m60, m30 = c[:4]
    if any(np.isnan(v) for v in (m120, m90, m60, m30)):
        return "빈 칸 있음"
    fails = []
    if not (m120 < m90 < m60 < m30):
        fails.append("단조 상승 아님")
    if m30 < 80:
        fails.append("30분 전 80 미만")
    if m120 >= 70:
        fails.append("120분 전 70 이상")
    return " + ".join(fails) if fails else "조건 충족(있으면 이상함)"

up["why"] = up["curve"].map(why)
print(up.groupby(["why", "item"]).size().unstack("item").fillna(0).astype(int))

# 유형별 개별 곡선 12개씩 (NOX, 무작위 seed 고정). 빈 칸은 선이 끊겨 보임
rng = np.random.default_rng(0)
fig, axes = plt.subplots(2, 3, figsize=(14, 7), sharey=True)
for ax, k in zip(axes.flat, ["평탄", "상승", "진동", "하강", "앞 사건 섞임", "값 부족"]):
    g = df[(df["type"] == k) & (df["item"] == "NOX")]["curve"].tolist()
    pick = rng.choice(len(g), size=min(12, len(g)), replace=False)
    for i in pick:
        ax.plot(x, g[i], alpha=0.7, marker=".")
    ax.axhline(90, color="gray", ls="--")
    ax.set_title(f"NOX {k} 샘플 {len(pick)}개")
    ax.set_ylim(30, 110)
fig.tight_layout()
fig.savefig(ROOT / "data" / "other_lead_samples.png", dpi=110)
print("저장: data/other_lead_samples.png")