'''
- shapes: 모양 판정
'''
HIGH = 0.90
EXCEED_LEVEL = 1.0

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