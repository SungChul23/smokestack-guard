'''
- 곡선 통계 test: 아주 긴 곡선을 생성했을 때 평균, 표준편차, 자기상관이 입력값과 가까운지 확인
'''
import numpy as np
import pytest
from synth import episode

N = 20000

# 곡선의 평균, 표준편차, 1차 자기상관
def stats_of(x):
    return x.mean(), x.std(), np.corrcoef(x[:-1], x[1:])[0, 1]

# (평균, 표준편차, 자기상관): 실측 참조 굴뚝에서 나올 만한 값들
@pytest.mark.parametrize("mean, std, phi", [
    (30, 6, 0.5),
    (30, 6, 0.8),
    (40, 5, 0.95),
    (25, 8, 0.7,)
])
def test_long_series_matches_reference(mean, std, phi):
    x = episode.normal_series(N, mean, std, phi, np.random.default_rng(7), hi = 70.0)
    m, s, p = stats_of(x)
    assert abs(m - mean) <= 0.10 * mean             # 평균 +- 10%
    assert abs(s - std) <= 0.10 * std               # 표준편차 +- 10%
    assert abs(p - phi) <= 0.10                     # 자기상관 +- 0.1

# 모든 값이 허용 범위 안
def test_long_series_stays_in_range():
    x = episode.normal_series(N, 30, 6, 0.8, np.random.default_rng(7), hi = 70.0)
    assert x.min() >= 0.0 and x.max() < 70.0