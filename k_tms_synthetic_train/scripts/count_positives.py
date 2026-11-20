'''
- count_positives: 모양별 에피소드당 양성 행 수 (라벨 v1: 지금 <90, 30분 또는 60분 뒤 >=90)
'''
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import yaml

from synth_train.assemble import assemble_episode

SHAPES = ["FALLING", "NEAR_HOLD", "IRREGULAR_RISE", "OSCILLATION",
          "SPIKE", "EXCEED", "PLATEAU", "OVER", "GRADUAL"]
REF = {"low": {"mean": 50.0, "std": 8.0, "phi": 0.8},      # 시험용 참조 굴뚝 통계(%)
       "high": {"mean": 78.0, "std": 5.0, "phi": 0.8}}
N = 300                                                    # 모양당 에피소드 수

with open(ROOT / "config" / "daily.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

# 양성 행 수: 지금 90% 미만이고 30분 또는 60분 뒤에 90% 이상
def positives(curve) -> int:
    n = 0
    for i, v in enumerate(curve):
        if v >= 90:
            continue
        if any(a >= 90 for a in curve[i + 1:i + 3]):
            n += 1
    return n

rng = np.random.default_rng(5)
for shape in SHAPES:
    ranges = cfg["shape_ranges"][shape]
    bg = cfg["ref_selection"]["groups"][ranges["group"]]["background_max"]
    counts = []
    for _ in range(N):
        curve, _, _ = assemble_episode(shape, rng, ranges, REF[ranges["group"]], cfg["episode"], bg)
        counts.append(positives(list(curve)))
    print(f"{shape:15s} 평균 {np.mean(counts):.2f}  (최소 {min(counts)}, 최대 {max(counts)})")