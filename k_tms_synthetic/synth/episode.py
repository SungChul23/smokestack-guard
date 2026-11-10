'''
- 값의 흐름 만들기: 굴뚝의 '기준대비율'이 30분마다 자연스럽게 흔들리는 줄을 생성

- 규칙 (AR(1))
    - 다음 값 = 평균 + phi x (직전 값 - 평균) + 랜덤 흔들림
        - 직전 값 근처에서 조금씩 움직이고 평균 쪽으로 끌려감
        - 랜덤 흔들림 = std x sqrt(1 - phi^2) 이면, 오래 지났을 때 값의 표준편차가 std

- 범위 (0 < x < 80)를 벗어난 값은 '깎지 않고' 흔들림을 다시 뽑음
'''
import math
import numpy as np

# 값 생성
def next_value(prev, mean, std, phi, rng, lo = 0.0, hi = 80.0, max_tries = 1000) -> float:
    if not -1 < phi < 1:
        raise ValueError(f"phi는 -1과 1 사이여야 함: {phi}")

    for _ in range(max_tries):
        if prev is None:
            candidate = mean + std * rng.standard_normal()
        else:
            noise_std = std * math.sqrt(1 - phi ** 2)
            candidate = mean + phi * (prev - mean) + noise_std * rng.standard_normal()

        if lo <= candidate < hi:
            return float(candidate)

    raise RuntimeError("허용 범위 안의 값을 만들지 못함. 평균, 표준편차, 범위 확인 필요")

# 정상 기준선을 생성(첫 값은 평균근처에서, 이후는 직전 값에서 이어사 생성)
def normal_series(n, mean, std, phi, rng, lo = 0.0, hi = 80.0, max_tries = 1000) -> np.ndarray:
    values = []
    prev = None
    for _ in range(n):
        prev = next_value(prev, mean, std, phi, rng, lo, hi, max_tries)
        values.append(prev)
    return np.array(values)

# 기준점 뒤로 이어지는 값 n개 생성
def continue_from(anchor, n, mean, std, phi, rng, lo = 0.0, hi = 80.0, max_tries = 1000) -> np.ndarray:
    values = []
    prev = anchor
    for _ in range(n):
        prev = next_value(prev, mean, std, phi, rng, lo, hi, max_tries)
        values.append(prev)
    return np.array(values)

# 기준점 앞에 붙일 값 n개 생성(AR(1)은 시간을 거꾸로 돌려도 같은 성질이라, 기준점에서 시간을 거꾸로 만든 후 순서를 뒤집음)
def lead_into(anchor, n, mean, std, phi, rng, lo = 0.0, hi = 80.0, max_tries = 1000) -> np.ndarray:
    backwards = continue_from(anchor, n, mean, std, phi, rng, lo, hi, max_tries)
    return backwards[::-1]