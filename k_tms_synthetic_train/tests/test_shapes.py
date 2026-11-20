'''
- shpes sampler test: 모양별 궤적 샘플러가 의도한 모양, 설정 범위, 재현성을 지키는지 확인
'''
from pathlib import Path
from synth_train import shapes
import numpy as np
import pytest
import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "daily.yaml"
SHAPES = ["FALLING", "SPIKE", "EXCEED", "PLATEAU", "OVER", "GRADUAL",
          "NEAR_HOLD", "IRREGULAR_RISE", "OSCILLATION", "NEAR_MISS"]

# 모양마다 가장 높은 값이 들어가야 하는 범위의 설정 키
PEAK_KEY = {
    "FALLING": "peak", "SPIKE": "peak", "EXCEED": "peak",
    "PLATEAU": "level", "OVER": "high", "GRADUAL": "entry", 
    "NEAR_HOLD": "peak", "IRREGULAR_RISE": "peak", "OSCILLATION": "peak", "NEAR_MISS": "peak"
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
        assert shapes.classify_shape(episode_with(traj), detail = True) == shape

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

# _n은 상한도 포함해서 뽑아야 함 (설정 [1, 2]면 1과 2 모두 나옴)
def test_n_includes_both_ends():
    rng = np.random.default_rng(0)
    assert {shapes._n(rng, [1, 2]) for _ in range(200)} == {1, 2}

# ratios에서 첫 사건을 찾아 세부 판정
def _detail(ratios):
    ev = shapes.find_events(ratios)[0]
    return shapes.classify_event_detail(ratios, ev)

# 진입 전 4칸(m120, m90, m60, m30)을 받아 앞 평소 8칸 + 진입 + 뒤 4칸으로 생성
def _with_lead(lead, entry = 0.95):
    return [0.5] * 8 + lead + [entry] + [0.5] * 4

# 근접 유지형: 4칸이 거의 평평 (변화폭 < 0.08), 모두 유호
def test_detail_near_hold():
    assert _detail(_with_lead([0.84, 0.85, 0.84, 0.86])) == "NEAR_HOLD"

# 불규칙 상승형: 전체 +0.08 이상 오르지만 단조는 아님(GRADUAL과 다름)
def test_detail_irregular_rise():
    assert _detail(_with_lead([0.60, 0.72, 0.70, 0.85])) == "IRREGULAR_RISE"

# 진동형: 변화폭 >= 0.08, 순변화 < 0.08, 방향이 번갈아 바뀜
def test_detail_oscilation():
    assert _detail(_with_lead([0.78, 0.88, 0.86, 0.80])) == "OSCILLATION"

# 4칸중 한 칸이 비면 (None) 새 유형이 아니라 OTHER
def test_detail_missing_cell_stays_other():
    assert _detail(_with_lead([0.84, None, 0.84, 0.86])) == "OTHER"

# 단조 상승 조건을 모주 만족하면 GRADUAL이 우선
def test_detail_gradual_wins_over_rise():
    assert _detail(_with_lead([0.55, 0.62, 0.70, 0.85])) == "GRADUAL"

# 기존 모양은 세부 판정을 거쳐도 그대로
def test_detail_passes_through_existing_shape():
    assert _detail([0.5] * 12 + [0.5, 0.95] + [0.5] * 4) == "SPIKE"

# 하강형: 4칸이 처음보다 0.08 이상 내려감 -> Falling
def test_detail_falling():
    assert _detail(_with_lead([0.88, 0.82, 0.76, 0.72])) == "FALLING"

# 한 번만 꺾이는 곡선도 진동형 (변화폭 >= 0.08, 순변화 < 0.08, 방향 전환 1회)
def test_detail_oscillation_one_turn():
    assert _detail(_with_lead([0.78, 0.88, 0.86, 0.80])) == "OSCILLATION"

# SPIKE는 진입 직전이 50%미만인 점프형도 생성해야 함
def test_spike_includes_jumps_cases():
    ranges = shape_ranges()["SPIKE"]
    rng = np.random.default_rng(3)
    below = 0
    for _ in range(300):
        traj = shapes.sample_trajectory("SPIKE", rng, ranges)
        if traj[1] < 50:
            below += 1
    assert below / 300 > 0.3

# NEAR_MISS 변형 3개(상승, 유지, 하락)가 모두 나옴, 90% 이상 칸은 없음
def test_near_miss_has_all_variants():
    ranges = shape_ranges()["NEAR_MISS"]
    rng = np.random.default_rng(4)
    rise = hold = fall = 0
    for _ in range(300):
        traj = shapes.sample_trajectory("NEAR_MISS", rng, ranges)
        assert max(traj) < 90
        top = traj.index(max(traj))
        if top == 0:
            fall += 1
        elif top >= 3:
            rise += 1
        else:
            hold += 1
    assert min(rise, hold, fall) > 20