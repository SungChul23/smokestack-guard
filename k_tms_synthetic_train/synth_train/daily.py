'''
- daily: 날짜 하나에 시작하는 합성 에피소드 목록 생성
'''
import zlib
import numpy as np
from datetime import datetime, timedelta
from synth_train import schedule, stats
from synth_train.assemble import assemble_episode

SLOTS_PER_DAY = 48

# 에피소드 seed
def make_seed(base_seed: int, day, item: str, shape: str, n: int) -> int:
    key = zlib.crc32(f"{item}-{shape}-{n}".encode("utf-8"))
    return int(np.random.SeedSequence([base_seed, int(f"{day:%Y%m%d}"), key]).generate_state(1)[0])

# 합성 굴뚝 코드
def make_stack_code(day, item: str, shape: str, n: int) -> str:
    return f"SYN-T-{day:%Y%m%d}-{item.upper()}-{shape}-{n:03d}"

# 당일 0시(KST)
def midnight(day) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo = schedule.KST)

# 에피소드가 day에 걸친 칸
def slots_on(ep: dict, day) -> list:
    start = midnight(ep["day"]) + timedelta(minutes = 30 * ep["start_slot"])
    base = midnight(day)
    out = []
    for i, v in enumerate(ep["curve"]):
        t = start + timedelta(minutes = 30 * i)
        if t.date() == day:
            out.append(((t - base) // timedelta(minutes = 30), float(v)))
    return out

# 참조 굴뚝을 궤적 첫 값을 보고 고르는 함수 생성
def _chooser(rows, cond, rng, chosen: dict):
    def pick(traj):
        cand = stats.filter_trajectory(rows, traj[0], cond)
        if cand.empty:
            return None
        row = stats.pick_one(cand, rng)
        chosen["ref"] = row
        return row
    return pick

# 에피소드 하나 생성
def make_episode(config: dict, ref_df, day, item: str, shape: str, n: int) -> dict:
    seed = make_seed(config["run"]["seed"], day, item, shape, n)
    rng = np.random.default_rng(seed)
    start_slot = int(rng.integers(0, SLOTS_PER_DAY))
    ranges = config["shape_ranges"][shape]
    cond = config["ref_selection"]["groups"][ranges["group"]]
    rows = stats.usable(ref_df[ref_df["item"] == item.upper()], config["ref_selection"]["min_valid"])
    chosen = {}
    curve, seg_start, seg_end = assemble_episode(
        shape, rng, ranges, _chooser(rows, cond, rng, chosen), config["episode"], cond["background_max"]
    )
    ref = chosen["ref"]
    return {
        "day": day, "item": item, "shape": shape, "n": n,
        "seed": seed, "start_slot": start_slot,
        "stack_code": make_stack_code(day, item, shape, n),
        "ref": {
            "fact_manage_nm": ref["fact_manage_nm"], "stack_code": str(ref["stack_code"]),
            "mean": float(ref["mean"]), "std": float(ref["std"]), "phi": float(ref["phi"]),
            "perm_std": float(ref["perm_std"]),
        },
        "curve": [float(v) for v in curve],
        "seg_start": seg_start, "seg_end": seg_end,
    }

# 날짜 하나에 시작하는 에피소드 전체
def episodes_started_on(config: dict, ref_df, day) -> list:
    eps = []
    for item, shapes in config["daily_episodes"].items():
        for shape, count in shapes.items():
            for n in range(1, count + 1):
                eps.append(make_episode(config, ref_df, day, item, shape, n))
    return eps