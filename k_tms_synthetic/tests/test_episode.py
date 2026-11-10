'''
- 값의 흐름 만들기 test
- 확인하는 것
    - 값이 항상 허용 범위(0 <= x < 80)안에 있는가
    - 만든 값의 평균, 표준편차, 직전 값과 닮은 정도가 목표와 맞는가
    - 범위 밖 값을 깍지 않고 다시 뽑는가
    - 같은 시드면 같은 결과인가, 불가능한 조건이면 에러를 내는가
    - 정해진 값의 앞, 뒤로 자연스럽게 이어 붙는가
'''
import numpy as np
import pytest
from synth import episode

# 평범한 값의 흐름이 기본 규칙을 지키는지 확인하는 테스트
def test_series_length_and_range():
    x = episode.normal_series(2000, mean = 30, std = 8, phi = 0.8, rng = np.random.default_rng(1))      # 시계열 2000개, 평균 30, 표준편차 8, 자기상관 0.8, 시드 1
    assert len(x) == 2000                                                                                    # 2000개가 만들어졌는지 확인
    assert x.min() >= 0 and x.max() < 80                                                                     # 값이 0 이상, 80 미만인지 확인

# 만들어진 시계열의 평균, 표준편차, 자기상관 값이 목표값에 가까운지 확인
def test_series_matches_target_statistics():
    x = episode.normal_series(20000, mean = 30, std = 8, phi = 0.8, rng = np.random.default_rng(2))
    assert abs(x.mean() - 30) < 1.0                                                                         # 평균이 목표 30에서 1 이내
    assert abs(x.std() - 8) < 0.8                                                                           # 표준편차가 목표 8에서 0.8 이내
    lag1 = np.corrcoef(x[:-1], x[1:])[0, 1]                                                            # 자기상관 = 닮은 정도
    assert abs(lag1 - 0.8) < 0.05                                                                           # 목표 자기상관(phi)이 0.8에서 0.05 이내

# 범위를 벗어난 값을 0이나 80으로 자르지 않고 다시 뽑는지 확인
def test_out_of_range_values_are_redrawn_not_clipped():
    x = episode.normal_series(3000, mean = 10, std = 20, phi = 0.5, rng = np.random.default_rng(3))
    assert (x == 0).sum() == 0                                                                              # 0인 값이 하나도 없어야 함
    assert x.min() >= 0 and x.max() < 80                                                                    # 모든 값은 0이상 80 미만이여야 함

# 같은 시드로 두 번 만들었을 때 완전히 같은 시계열이 나오는지 확인
def test_same_seed_gives_same_series():
    a = episode.normal_series(100, 30, 8, 0.8, np.random.default_rng(7))                                # 7시드로 100개 생성
    b = episode.normal_series(100, 30, 8, 0.8, np.random.default_rng(7))                                # 7시드로 100개 생성
    assert np.array_equal(a, b)                                                                              # 두 결과의 값까지 완전히 같은지 확인

# 범위 안의 값을 만들 수 없을 때, 무한히 돌지 않고 에러를 내는지 확인
def test_impossible_range_raises():
    with pytest.raises(RuntimeError):                                                                               # 시도 횟수를 다 쓰고 실패하면 RuntimeError가 나야 통과
        episode.normal_series(10, mean = 500, std = 1, phi = 0.5, rng = np.random.default_rng(1), max_tries = 50)   

# 기준값(62)에서 이어 붙인 시계열이 기준값 근처에서 시작하고, 개수와 범위를 지키는지 확인
def test_continue_from_starts_near_anchor():
    x = episode.continue_from(62, 48, mean = 60, std = 5, phi = 0.9, rng = np.random.default_rng(1))    # 기준값 62에서 이어지는 48개를 만듬
    assert len(x) == 48                                                                                      # 요청한 개수만큼 만들어 졌는지 확인
    assert abs(x[0] - 62) < 15                                                                               # 첫 값이 기준값 62에서 크게 벗어나지 않는지 확인
    assert x.max() < 80                                                                                      # 정상 구간이라 80% 미만인지

# 기준값(62)로 이어지는 앞 구간이 기준값 근처에서 끝나고, 개수를 지키는지 확인
def test_lead_into_ends_near_anchor():
    x = episode.lead_into(62, 48, mean = 60, std = 5, phi = 0.9, rng = np.random.default_rng(1))    # 기준값 62 직전까지 이어지는 48개의 시계열 생성
    assert len(x) == 48                                                                                  # 요청한 개수만큼 만들어 졌는지
    assert abs(x[-1] -62) < 15                                                                           # 마지막 값이 기준값 62에서 크게 벗어나지 않는지 확인

# 앞 구간이 시간 순서대로 뒤집혀 있는지 확인
def test_lead_into_is_in_time_order():
    x = episode.lead_into(62, 200, mean = 30, std = 8, phi = 0.8, rng = np.random.default_rng(5))   # 평균 30인 굴뚝에서 62로 이어지는 200개의 시계열 생성
    assert x[:20].mean() < x[-3:].mean()                                                                 # 맨 앞 20개의 평균이 맨 뒤 3개의 평균보다 작아야 함