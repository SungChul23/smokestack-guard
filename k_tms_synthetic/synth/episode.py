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

# 직전 값에서 다음 기준대비율 값 하나를 생성. 범위 밖이면 깎지 않고 다시 뽑음
def next_value(prev, mean, std, phi, rng, lo = 0.0, hi = 80.0, max_tries = 1000) -> float:  
    if not -1 < phi < 1:                                                                        # phi가 -1~1 밖이면 AR(1)이 불안정이므로 미리 막음
        raise ValueError(f"phi는 -1과 1 사이여야 함: {phi}")                                     

    for _ in range(max_tries):                                                                  # 범위 안의 값이 나올 때까지 최대 max_tries번 다시 뽑음
        if prev is None:                                                                        # prev가 None이면 직전 값이 없는 '맨 처음 값'
            candidate = mean + std * rng.standard_normal()                                 # 맨 처음 값: 평균 근처에서 표준편차만큼 흔들리게 뽑음
        else:                                                                                   
            noise_std = std * math.sqrt(1 - phi ** 2)                                      # 랜덤 흔들림의 크기: 장기적으로 값의 표준치가 std가 되도록 보정
            candidate = mean + phi * (prev - mean) + noise_std * rng.standard_normal()     # 직전 값에서 평균 쪽으로 phi만큼 끌려오고, 랜덤 흔들림을 더함

        if lo <= candidate < hi:                                                                # 허용 범위 안이면 이 값을 채택
            return float(candidate)

    raise RuntimeError("허용 범위 안의 값을 만들지 못함. 평균, 표준편차, 범위 확인 필요")          # 계속 범위 밖이면 조건이 불가능한 것이므로 에러로 앎림

# 처음부터 끝까지 평범한 값 n개의 줄을 생성(첫 값은 평균근처에서, 이후는 직전 값에서 이어서 생성)
def normal_series(n, mean, std, phi, rng, lo = 0.0, hi = 80.0, max_tries = 1000) -> np.ndarray:
    values = []                                                                             # 만든 값을 차례로 모아 둘 빈 리스트
    prev = None                                                                                   # 직전 값. None으로 시작하면 next_value가 첫 값을 평균 근처에서 뽑음
    for _ in range(n):                                                                            # 값 n개를 하나씩 만듬
        prev = next_value(prev, mean, std, phi, rng, lo, hi, max_tries)                    # 직전 값에서 다음 값을 만들고, 이 값이 다시 직전 값이 되어 이어짐
        values.append(prev)                                                                       # 만든 값을 리스트에 추가
    return np.array(values)                                                                       # 리스트를 numpy 배열로 바꿔 돌려줌

# 기준점 뒤로 이어지는 값 n개 생성. 정해진 모양의 마지막 값에서 평범한 값으로 돌아오는 구간에서 사용
def continue_from(anchor, n, mean, std, phi, rng, lo = 0.0, hi = 80.0, max_tries = 1000) -> np.ndarray:
    values = []                                                                             # 만든 값을 차례로 모아 둘 빈 리스트
    prev = anchor                                                                            # 출발점을 기준으로 설정. normal_series와 달리 None이 아니라 정해진 값에서 시작
    for _ in range(n):                                                                            # 값 n개를 하나씩 만듬
        prev = next_value(prev, mean, std, phi, rng, lo, hi, max_tries)                    # 직전 값에서 다음 값을 만듬. 첫 값은 기준점 근처에서 시작해 점점 평균 쪽으로 끌려감
        values.append(prev)                                                                       # 만든 값을 리스트에 추가
    return np.array(values)                                                                       # 리스트를 numpy 배열로 바꿔 돌려줌

# 기준점 앞에 붙일 값 n개 생성(AR(1)은 시간을 거꾸로 돌려도 같은 성질이라, 기준점에서 시간을 거꾸로 만든 후 순서를 뒤집음)

# 거꾸로 만든 값 (continue_from) : [60, 55, 48]   ← 기준점에서 멀어지는 순서
# 뒤집은 결과   (backwards[::-1]) : [48, 55, 60]   ← 시간 순서, 마지막(60)이 기준점(62) 근처
# 이어 붙인 전체                  : [48, 55, 60, 62(기준점), ...]

def lead_into(anchor, n, mean, std, phi, rng, lo = 0.0, hi = 80.0, max_tries = 1000) -> np.ndarray: 
    backwards = continue_from(anchor, n, mean, std, phi, rng, lo, hi, max_tries)    # 기준점에서 '시간을 거꾸로'도린 값을 만듬 
    return backwards[::-1]                                                                                          # 거꾸로 만든 순서를 뒤집어 과거 -> 기준점 직전 시간 순서로 돌려줌
