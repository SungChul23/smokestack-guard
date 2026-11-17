'''
- 궤적 구현: 정해진 값(궤적)을 곡선의 정해진 칸에 끼워넣고, 앞뒤를 자연스럽게 이음
- 앞 구간: 궤적의 첫 값에서 시간을 거꾸로 만들어 뒤집음
- 뒤 구간: 궤적 마지막 값에서 평균 쪽으로 이어서 내려옴
'''
import numpy as np
from synth import episode

# n칸 곡선 하나를 만들어 돌려줌
def inject(n, trajectory, start_step, mean, std, phi, rng, background_max, return_max = 90.0, lo = 0.0) -> np.ndarray:
    traj = np.asarray(trajectory, dtype = float)
    first = start_step -1
    end = first + len(traj)
    if first < 0 or end > n:
        raise ValueError(f"궤적이 에피소드 밖으로 나감: start_step {start_step}, 길이 {len(traj)}, 전체 {n}")
    lead = episode.lead_into(traj[0], first, mean, std, phi, rng, lo = lo, hi = background_max)
    tail = episode.continue_from(traj[-1], n - end, mean, std, phi, rng, lo = lo, hi = return_max)
    return np.concatenate([lead, traj, tail])