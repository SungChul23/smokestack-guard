'''
- pack: 에피소드 곡선을 날짜 하나의 슬롯별 스냅샷을 묶음
'''
from datetime import timedelta
from synth_train import daily, schedule, snapshot

AREA_NM = "합성지역"

# 날짜 하나의 슬롯 48개를 스냅샷으로 만듬
def pack_day(config: dict, episodes: list ,day) -> list:
    slot_min = config["snapshot"]["slot_min"]
    offset = config["snapshot"]["run_ts_offset_min"]
    by_slot = {s: [] for s in range(daily.SLOTS_PER_DAY)}
    for ep in episodes:
        for slot, pct in daily.slots_on(ep, day):
            by_slot[slot].append((ep, pct))

    base = daily.midnight(day)
    out = []
    for s in range(daily.SLOTS_PER_DAY):
        t = base + timedelta(minutes = slot_min * s)
        mesure_dt = schedule.format_mesure_dt(t)
        items = []
        for ep, pct in sorted(by_slot[s], key = lambda x: x[0]["stack_code"]):
            code = ep["stack_code"]
            measures = {ep["item"]: snapshot.ratio_to_measure(pct, ep["ref"]["perm_std"])}
            items.append(snapshot.make_item(
                AREA_NM, code.replace("SYN-", "합성사업장-"), code, mesure_dt, measures))
        out.append({
            "slot": s,
            "mesure_dt": mesure_dt,
            "run_ts": schedule.to_run_ts(t + timedelta(minutes=offset)),
            "snapshot": snapshot.make_snapshot(items),
            "rows": len(items),
        })
    return out