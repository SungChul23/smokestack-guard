'''
- shapes: 모양 판정
'''
import numpy as np

HIGH = 0.90
EXCEED_LEVEL = 1.0
MAX_TRIES = 1000
LEAD_MOVE = 0.08
LEAD_CAP = 89.9
NEAR_MISS_MIN = 0.80

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

# 사건 하나의 세부 모양: classify_event가 OTHER일 때만 진입 전 4칸으로 더 나눔
def classify_event_detail(ratios, event) -> str:
    shape = classify_event(ratios, event)
    if shape != "OTHER":                                                        # 기존 모양은 그대로 통과
        return shape

    start = event["rows"][0]
    lead = [_at(ratios, start - k) for k in (4, 3, 2, 1)]     # 120분 전 -> 30분 전 순서
    if None in lead:                                                            # 한 칸이라도 비면 나누지 않음
        return "OTHER"

    spread = max(lead) - min(lead)                                         # 4칸 이내 변화폭
    net = lead[3] - lead[0]                                                # 처음 -> 마지막 변화
    steps = [lead[i + 1] - lead[i] for i in range(3)]                     # 칸마다의 변화 3개
    turns = sum(1 for a, b in zip(steps, steps[1:]) if a * b < 0)          # 방향이 바뀐 횟수

    if net >= LEAD_MOVE:
        return "IRREGULAR_RISE"
    if spread >= LEAD_MOVE and abs(net) < LEAD_MOVE and turns >= 1:
        return "OSCILLATION"
    if spread < LEAD_MOVE:
        return "NEAR_HOLD"
    if net <= -LEAD_MOVE:
        return "FALLING"
    return "OTHER"

# 시계열 모양, 사건이 없다면 None, 둘 이상이면 오류
def classify_shape(ratios, detail = False):
    events = find_events(ratios)
    if not events:
        vals = [r for r in ratios if r is not None]
        if detail and vals and max(vals) >= NEAR_MISS_MIN:
            return "NEAR_MISS"
        return None
    if len(events) > 1:
        raise ValueError(f"사건이 {len(events)}개라 모양을 하나로 정할 수 없음")
    classify = classify_event_detail if detail else classify_event
    return classify(ratios, events[0])

def _u(rng, lo_hi) -> float:
    return float(rng.uniform(lo_hi[0], lo_hi[1]))

def _n(rng, lo_hi) -> int:
    return int(rng.integers(lo_hi[0], lo_hi[1] + 1))

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

def _cap(vals) -> list:
    return [min(float(v), LEAD_CAP) for v in vals]

# 진입부 공용: 90% 이상 구간 n칸 + 복귀 값(진입 전 4칸 위에 붙임)
def _entry(rng, r) -> list:
    n = _n(rng, r["high_len"])
    top = _u(rng, r["peak"])
    return _highs(rng, n, 90, top) + [_u(rng, r["after"])]

# 근접 유지형: 기준값 근처에서 조금씩만 흔들림 (변화폭 < 8)
def _draw_near_hold(rng, r):
    base = _u(rng, r["base"])
    lead = [base + _u(rng, r["wobble"]) for _ in range(4)]
    return _cap(lead) + _entry(rng, r)

# 불규칙 상승형: 시작에서 끝으로 오르되 가운데 두 칸에 잡음을 줘 단조를 깸
def _draw_irregular_rise(rng, r):
    start = _u(rng, r["start"])
    end = _u(rng, r["end"])
    mids = [start + (end - start) * f + _u(rng, r["noise"]) for f in (1 / 3, 2 / 3)]
    return _cap([start] + mids + [end]) + _entry(rng, r)

# 진동형: 올랐다 내렸다 다시 오름(또는 반대). 방향이 번갈아 바뀜
def _draw_oscillation(rng, r):
    base = _u(rng, r["base"])
    sign = 1 if rng.integers(2) == 0 else -1
    a1, a2, a3 = (_u(rng, r["amp"]) for _ in range(3))
    v1 = base + sign * a1
    v2 = v1 - sign * a2
    if rng.integers(2) == 0:
        v3 = v2 + sign * a3
    else:
        v3 = v2 - sign * a3 / 2
    return _cap([base, v1, v2, v3]) + _entry(rng, r)

# 하강형: 진입 전 4칸이 내려가는 곡선
def _draw_falling(rng, r):
    v = _u(rng, r["start"])
    lead = [v]
    for _ in range(3):
        v -= _u(rng, r["step_drop"])
        lead.append(v)
    return _cap(lead) + _entry(rng, r)

# 정상 근접형: 90%에 닿지 않고 80~89.9%까지만 오르거나 머무르거나 내려옴
def _draw_near_miss(rng, r):
    peak = _u(rng, r["peak"])
    kind = int(rng.integers(3))
    if kind == 0:
        n = _n(rng, r["ramp_steps"])
        start = _u(rng, r["start"])
        body = [start + (peak - start) * (i + 1) / n for i in range(n)]
    elif kind == 1:
        body = _highs(rng, _n(rng, r["hold_len"]), 80, peak)
    else:
        body = [peak]
        for _ in range(_n(rng, r["fall_steps"])):
            body.append(body[-1] - _u(rng, r["step_drop"]))
    return body + [_u(rng, r["after"])]

_DRAWERS = {
    "SPIKE": _draw_spike, "EXCEED": _draw_exceed, "PLATEAU": _draw_plateau,
    "OVER": _draw_over, "GRADUAL": _draw_gradual, "FALLING": _draw_falling,
    "NEAR_HOLD": _draw_near_hold, "IRREGULAR_RISE": _draw_irregular_rise, "OSCILLATION": _draw_oscillation, "NEAR_MISS": _draw_near_miss
}

# 앞 12칸, 뒤 8칸을 정상값으로 채워 모양 판정
def _judge(traj_pct):
    return classify_shape([0.5] * 12 + [p / 100 for p in traj_pct + [0.5] * 8], detail = True)

# 모양 구간 궤적 하나, 의도가 다른 모양이면 rng로 다시 뽑음
def sample_trajectory(shape, rng, ranges) -> list:
    if shape not in _DRAWERS:
        raise ValueError(f"모르는 모양: {shape}")
    for _ in range(MAX_TRIES):
        traj = _DRAWERS[shape](rng, ranges)
        if traj is None:
            continue
        traj = [round(float(v), 1) for v in traj]
        if _judge(traj) == shape:
            return traj
    raise RuntimeError(f"{shape} 범위에서 {MAX_TRIES}번 뽑아도 모양이 안 맞음, 범위를 확인하세요")