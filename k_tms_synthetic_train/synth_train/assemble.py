'''
- assemble: 에피소드 하나 조립 (앞 정상 구간 + 모양 구간 + 뒤 복귀 구간)
'''
from synth_train import shapes
from synth_train.scenarios import trajectory

MAX_TRIES = 200

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
        curve = trajectory.inject(
            n, traj, warmup + 1,                       # start_step은 1부터 센다
            r["mean"], r["std"], r["phi"], rng,
            background_max, ep["return_max"],
        )
        if shapes.classify_shape((curve / 100).tolist()) == shape:
            return curve, warmup, warmup + len(traj)
    raise RuntimeError(f"{shape} 에피소드를 {MAX_TRIES}번 조립해도 모양이 안 맞음")