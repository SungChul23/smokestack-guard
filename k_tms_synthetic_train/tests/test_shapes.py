'''
- shpes sampler test: 모양별 궤적 샘플러가 의도한 모양, 설정 범위, 재현성을 지키는지 확인
'''
from pathlib import Path
from synth_train import shapes
import numpy as np
import pytest
import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "daily.yaml"
SHAPES = ["OTHER", "SPIKE", "EXCEED", "PLATEAU", "OVER", "GRADUAL"]

# 모양마다 가장 높은 값이 들어가야 하는 범위의 설정 키
PEAK_KEY = {
    "OTHER": "peak", "SPIKE": "peak", "EXCEED": "peak",
    "PLATEAU": "level", "OVER": "high", "GRADUAL": "entry", 
}

def shape_ranges():
    with open(CONFIG, encoding = "utf-8") as f:
        return yaml.safe_load(f)["shape_ranges"]

# 시계열 모양 테스트와 같은 방식으로 궤적을 정상 배경 사이에 끼움
def episode_with(traj_pct, lead = 0.5, n_lead = 12, n_tail = 8):
    return [lead] * n_lead + [p/100 for p in traj_pct] + [0.5] * n_tail

# 궤적 500개가 모두 의도한 모양으로 판정
@pytest.mark.parametrize("shape", SHAPES)
def test_samples_match_shape(shape):
    ranges = shape_ranges()[shape]
    rng = np.random.default_rng(1)
    for _ in range(500):
        traj = shapes.sample_trajectory(shape, rng, ranges)
        assert shapes.classify_shape(episode_with(traj)) == shape

# 가장 높은 값이 설정 범위 안이고, 궤적이 서로 달라짐
@pytest.mark.parametrize("shape", SHAPES)
def test_samples_in_range(shape):
    ranges = shape_ranges()[shape]
    lo, hi = ranges[PEAK_KEY[shape]]
    rng = np.random.default_rng(2)
    seen = set()
    for _ in range(200):
        traj = shapes.sample_trajectory(shape, rng, ranges)
        assert all(v >= 0 for v in traj)
        assert lo <= max(traj) <= hi
        seen.add(tuple(round(v, 1) for v in traj))
    assert len(seen) > 50

# 같은 seed면 같은 궤적, 다른 seed면 다른 궤적
@pytest.mark.parametrize("shape", SHAPES)
def test_reproducible_seed(shape):
    ranges = shape_ranges()[shape] 
    a = shapes.sample_trajectory(shape, np.random.default_rng(7), ranges)
    b = shapes.sample_trajectory(shape, np.random.default_rng(7), ranges)
    c = shapes.sample_trajectory(shape, np.random.default_rng(8), ranges)
    assert a == b
    assert a != c

# 모르는 모양 이름은 오류
def test_unknown_shape_raises():
    with pytest.raises(ValueError):
        shapes.sample_trajectory("NOPE", np.random.default_rng(1), {})