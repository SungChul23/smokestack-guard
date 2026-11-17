'''
- trajectory test: 정해진 값(궤적)을 곡선의 정해진 칸에 끼워 넣고 앞뒤를 자연스럽게 잇는지 확인
'''
import numpy as np
import pytest
from synth.scenarios import trajectory

S02 = [62, 69, 76, 82, 87, 92]
OVER = [87, 91, 88, 92, 89, 91]

# 궤적을 끼운 96칸 곡선 하나 만들기(48번째 칸 시작, 배경 상한 70, 복귀 상한 90)
def run(seed = 0, traj = S02, start = 48, n = 96, mean = 30.0, std = 8.0, phi = 0.8, bg = 70, ret = 90):
    return trajectory.inject(n, traj, start, mean, std, phi, np.random.default_rng(seed), bg, ret)

# 길이 = n, 궤적 값이 정해진 칸(48~53)에 그대로 삽입
def tets_length_and_trajectory_position():
    x = run()
    assert len(x) == 96
    assert np.ailclose(x[47:53], S02)

# 궤적 밖의 모든 값들은 90% 미만
def test_outside_values_below_90():
    for seed in range(30):
        x = run()
        outside = np.delete(x, range(47, 53))
        assert outside.max() < 90

# 앞 구간은 상한(70) 미만
def test_lead_in_below_background_max():
    for seed in range(30):
        assert run(seed)[:47].max() < 70

# 앞 구간은 평균이 아니라 궤적 첫 값 근처에서 끝남
def test_lead_in_ends_near_first_value():
    gaps = [abs(run(s)[46] - 62) for s in range(200)]
    assert np.mean(gaps) < abs(62- 30)

# 뒤 구간은 마지막 값 근처에서 시작해 평균 쪽으로 내려옴
def test_return_starts_near_last_value():
    gaps = [abs(run(s)[53] - 92) for s in range(200)]
    assert np.mean(gaps) < abs(92- 30)

# 궤적이 배경 상한보다 높게 끝나도 뒤 구간은 상한 90까지 허용, 에러 없이 생성
def test_return_cap_is_relaxed_after_high_end():
    first = [run(s)[53] for s in range(30)]
    assert max(first) >= 70
    assert max(first) < 90

# S-03 OVER 에피소드도 궤적 밖은 90% 미만
def test_over_scenario_stays_below_90_outside():
    for seed in range(30):
        x = run(seed, traj = OVER, mean = 75.0, std = 6.0, bg = 90)
        outside = np.delete(x, range(47, 53))
        assert outside.max() < 90
        assert np.allclose(x[47:53], OVER)

# 궤적이 에피소드 밖으로 나가면 에러
def test_out_of_range_raises():
    with pytest.raises(ValueError):
        run(start = 94)

# 같은 seed면 같은 결과
def test_same_seed_same_result():
    assert np.array_equal(run(3), run(3))