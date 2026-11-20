'''
- assemble: 에피소드 하나 조립 (앞 정상 구간 + 모양 구간 + 뒤 복귀 구간)
'''
import numpy as np
from synth_train import shapes, snapshot
from synth_train.scenarios import trajectory

MAX_TRIES = 200

# 곡선 값을 파일에 쓰일 문자열 기준으로 맞춤, 문자열에서 되돌린 비율과 같아짐
def _quantize(curve, perm_std: float):
    limit = float(snapshot.format_limit(perm_std))
    return np.array([float(snapshot.format_value(v / 100 * perm_std)) / limit * 100 for v in curve])

# curve(%), 모양 구간 시작·끝 위치를 돌려줌: curve[start:end]가 모양 구간
def assemble_episode(shape, rng, ranges, ref, ep, background_max):
    warmup = ep["warmup_steps"]
    ref_of = ref if callable(ref) else (lambda traj: ref)
    for _ in range(MAX_TRIES):
        traj = shapes.sample_trajectory(shape, rng, ranges)
        r = ref_of(traj)
        if r is None:
            continue
        n = warmup + len(traj) + ep["return_steps"]
        try:
            curve = trajectory.inject(
                n, traj, warmup + 1,                    
                r["mean"], r["std"], r["phi"], rng,
                background_max, ep["return_max"],
            )
        except RuntimeError:
            continue
        if "perm_std" in r:
            curve = _quantize(curve, r["perm_std"])
        try:
            got = shapes.classify_shape((curve / 100).tolist(), detail = True)
        except ValueError:                               
            continue
        if got == shape:
            return curve, warmup, warmup + len(traj)
    raise RuntimeError(f"{shape} 에피소드를 {MAX_TRIES}번 조립해도 모양이 안 맞음")