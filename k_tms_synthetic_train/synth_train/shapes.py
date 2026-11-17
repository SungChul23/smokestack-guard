'''
- shapes: 모양 판정
'''
import numpy as np

HIGH = 0.90
EXCEED_LEVEL = 1.0
MAX_TRIES = 1000

# 사건 목록
def find_events(ratios) -> list:
    highs = [i for i, r in enumerate(ratios) if r is not None and r >= HIGH]
    events = []
    prev = None
    for i in highs:
        gap = None if prev is None else i - prev

        if prev is None or gap > 2:
            events.append({"rows": [i], "entries": 1})
        else:
            events[-1]["rows"].append(i)
            if gap > 1:
                events[-1]["entries"] += 1

        prev = i
    return events

# i번째 값. 범위 밖이면 None
def _at(ratios, i):
    return ratios[i] if 0 <= i < len(ratios) else None

# 사건 하나의 모양
def classify_event(ratios, event) -> str:
    rows = event["rows"]
    start = rows[0]
    high_rows = len(rows)
    entries = event["entries"]
    peak = max(ratios[i] for i in rows)
    exceed_rows = sum(1 for i in rows if ratios[i] >= EXCEED_LEVEL)
    m30, m60, m90, m120 = (_at(ratios, start - k) for k in (1, 2, 3, 4))

    if exceed_rows >= 3:
        return "EXCEED"
    if high_rows >= 4 and peak < EXCEED_LEVEL and entries <= 2:
        return "PLATEAU"
    if entries >= 3:
        return "OVER"
    if high_rows <= 2 and m30 is not None and m30 < 0.70:
        return "SPIKE"
    if (None not in (m30, m60, m90, m120)
        and m120 < m90 < m60 < m30
        and m30 >= 0.80 and m120 < 0.70
        ):
        return "GRADUAL"
    return "OTHER"

# 시계열 모양, 사건이 없다면 None, 둘 이상이면 오류
def classify_shape(ratios):
    events = find_events(ratios)
    if not events:
        return None
    if len(events) > 1:
        raise ValueError(f"사건이 {len(events)}개라 모양을 하나로 정할 수 없음")
    return classify_event(ratios, events[0])

def _u(rng, lo_hi) -> float:
    return float(rng.uniform(lo_hi[0], lo_hi[1]))

def _n(rng, lo_hi) -> int:
    return int(rng.integers(lo_hi[0], lo_hi[1]))

# 값 n개: 가장 높은 값이 정확히 top, 나머지는 float~top 사이
def _highs(rng, n, floor, top) -> list:
    vals = [float(v) for v in rng.uniform(floor, top, n)]
    vals[int(rng.integers(n))] = float(top)
    return vals

def _draw_spike(rng, r):
    peak = _u(rng, r["peak"])
    n = _n(rng, r["peak_len"])
    return [_u(rng, r["before"]), _u(rng, r["before"])] \
        + _highs(rng, n, 90, peak) \
        + [_u(rng, r["after"]), _u(rng, r["after"])]

def _draw_exceed(rng, r):
    peak = _u(rng, r["peak"])
    n = _n(rng, r["exceed_len"])
    return [_u(rng, r["before"])] \
        + _highs(rng, n, 100, peak) \
        + [_u(rng, r["after"]), float(rng.uniform(60, 89))]

def _draw_plateau(rng, r):
    level = _u(rng, r["level"])
    n = _n(rng, r["hold_len"])
    return [_u(rng, r["before"])] \
        + _highs(rng, n, 90, level) \
        + [_u(rng, r["after"])]

def _draw_over(rng, r):
    entries = _n(rng, r["entries"])
    top = _u(rng, r["high"])
    highs = _highs(rng, entries, 90, top)
    out = []
    for h in highs:                       # 낮음, 높음, 낮음, 높음 ...
        out += [_u(rng, r["low"]), h]
    return out + [_u(rng, r["low"])]

def _draw_gradual(rng, r):
    n = _n(rng, r["ramp_steps"])
    ramp = [_u(rng, r["ramp_start"])]
    for _ in range(n - 1):
        ramp.append(ramp[-1] + _u(rng, r["step_rise"]))
    if max(ramp) >= 90:                   # 올라가는 도중에 90%를 넘으면 안 됨
        return None
    return ramp + [_u(rng, r["entry"])]

def _draw_other(rng, r):
    n = _n(rng, r["high_len"])
    top = _u(rng, r["peak"])
    return [_u(rng, r["before"])] \
        + _highs(rng, n, 90, top) \
        + [float(rng.uniform(70, 89))]

_DRAWERS = {
    "SPIKE": _draw_spike, "EXCEED": _draw_exceed, "PLATEAU": _draw_plateau,
    "OVER": _draw_over, "GRADUAL": _draw_gradual, "OTHER": _draw_other,
}

# 앞 12칸, 뒤 8칸을 정상값으로 채워 모양 판정
def _judge(traj_pct):
    return classify_shape([0.5] * 12 + [p / 100 for p in traj_pct + [0.5] * 8])

# 모양 구간 궤적 하나, 의도가 다른 모양이면 rng로 다시 뽑음
def sample_trajectory(shape, rng, ranges) -> list:
    if shape not in _DRAWERS:
        raise ValueError(f"모르는 모양: {shape}")
    for _ in range(MAX_TRIES):
        traj = _DRAWERS[shape](rng, ranges)
        if traj is None:
            continue
        tarj = [round(float(v), 1) for v in traj]
        if _judge(traj) == shape:
            return traj
    raise RuntimeError(f"{shape} 범위에서 {MAX_TRIES}번 뽑아도 모양이 안 맞음, 범위를 확인하세요")