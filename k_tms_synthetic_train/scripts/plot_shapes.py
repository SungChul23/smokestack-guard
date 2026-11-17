'''
- plot_shapes: 모양별 합성 곡선 샘플을 그려 눈으로 확인 (T020)
'''
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from synth_train.assemble import assemble_episode

ROOT = Path(__file__).resolve().parent.parent
SHAPES = ["OTHER", "SPIKE", "EXCEED", "PLATEAU", "OVER", "GRADUAL"]
REF = {"mean": 45.0, "std": 8.0, "phi": 0.8}      # 시험용 참조 굴뚝 통계(%)
N = 6                                              # 모양당 곡선 수

with open(ROOT / "config" / "daily.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharey=True)
rng = np.random.default_rng(11)
for ax, shape in zip(axes.flat, SHAPES):
    ranges = cfg["shape_ranges"][shape]
    bg = cfg["ref_selection"]["groups"][ranges["group"]]["background_max"]
    for _ in range(N):
        curve, start, end = assemble_episode(shape, rng, ranges, REF, cfg["episode"], bg)
        ax.plot(curve, alpha=0.8)
    ax.axhline(90, color="red", linestyle="--", linewidth=0.8)
    ax.axhline(100, color="black", linestyle=":", linewidth=0.8)
    ax.set_title(shape)
    ax.set_xlabel("slot (30min)")
axes[0][0].set_ylabel("ratio %")

out = ROOT / "out"
out.mkdir(exist_ok=True)
fig.tight_layout()
fig.savefig(out / "shapes_preview.png", dpi=110)
print("saved:", out / "shapes_preview.png")