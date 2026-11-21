'''
- plot_real_other: 실측 OTHER(단서 있음) 사건 곡선을 겹쳐 그려 큰 그림을 봄
'''
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False        # 마이너스 기호 깨짐 방지
import numpy as np

from synth_train import real_events

series = real_events.load_series(
    ROOT / "data" / "other_series.csv", "2026-10-30 00:00", "2026-11-12 23:30"
)

# 성분별로 OTHER + 단서 있음 사건의 곡선(%)을 모음
curves = {"NOX": [], "SOX": []}
for (item, fact, code), ratios in series.items():
    for ev in real_events.extract_events(ratios):
        if ev["shape"] == "OTHER" and ev["cue"]:
            # None은 nan으로 바꿔 통계 계산이 되게 함
            curves[item].append([np.nan if v is None else v * 100 for v in ev["curve"]])

x = [-120, -90, -60, -30, 0, 30, 60]               # 사건 첫 90% 이상 행 기준 분(0 = 진입)
fig, axes = plt.subplots(1, 2, figsize=(13, 6), sharey=True)
for ax, item in zip(axes, ["NOX", "SOX"]):
    arr = np.array(curves[item])
    # 칸별 분포: 상자 = 25~75%, 수염 = 5~95%, 빈 칸(nan)은 제외
    cols = [col[~np.isnan(col)] for col in arr.T]
    ax.boxplot(cols, positions=x, widths=18, whis=(5, 95), showfliers=False,
               manage_ticks=False)
    ax.plot(x, np.nanmedian(arr, axis=0), color="red", lw=2, marker="o", label="중앙값")
    ax.axhline(90, color="gray", ls="--")
    ax.set_ylim(30, 110)
    ax.set_title(f"{item} OTHER (단서 있음) n={len(arr)}")
    ax.set_xlabel("진입 기준 분 (0 = 첫 90% 이상 행)")
    ax.set_xticks(x)
    ax.legend()
axes[0].set_ylabel("허용기준 대비 (%)")
fig.tight_layout()
fig.savefig(ROOT / "data" / "other_real_curves.png", dpi=120)
print("저장:", ROOT / "data" / "other_real_curves.png")