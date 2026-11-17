'''
- pack test: 에피소드를 슬롯별 스냅샷으로 묶었을 때 구조, 시각, 추적, 크기 확인
'''
import json
import pytest
from collections import Counter
from datetime import date, timedelta, timezone
from synth_train import daily, pack, schedule, snapshot

D = date(2026, 11, 16)
PREV = date(2026, 11, 15)

@pytest.fixture(scope = "module")
def eps(config, ref_df):
    return(daily.episodes_started_on(config, ref_df, PREV)
           + daily.episodes_started_on(config, ref_df, D))

@pytest.fixture(scope = "module")
def day_snaps(config, eps):
    return pack.pack_day(config, eps, D)

# 슬롯 48개당 스냅샷 1개
def test_one_snapshot_per_slot(day_snaps):
    assert [s["slot"] for s in day_snaps] == list(range(48))
    assert all(s["rows"] == len(s["snapshot"]["response"]["body"]["items"]) for s in day_snaps)
    assert all(s["snapshot"]["response"]["header"]["totalCount"] == s["rows"] for s in day_snaps)

# 같은 굴뚝, 측정시각이 하루 안에서 하나만 나타남
def test_key_appears_once(day_snaps):
    keys = [(it["stack_code"], it["mesure_dt"])
            for s in day_snaps for it in s["snapshot"]["response"]["body"]["items"]]
    assert len(keys) == len(set(keys))

# run-ts = 측정 시각 + 70분
def test_run_ts_is_mesure_plus_70min(day_snaps):
    for s in day_snaps:
        mesure_utc = schedule.parse_kst(s["mesure_dt"]).astimezone(timezone.utc)
        assert s["run_ts"] == mesure_utc + timedelta(minutes = 70)
        assert all(it["mesure_dt"] == s["mesure_dt"]
                   for it in s["snapshot"]["response"]["body"]["items"])

# 굴뚝 코드로 에피소드 역산 가능
def test_trace_episode(day_snaps, eps):
    by_code = {e["stack_code"]: e for e in eps}
    for s in day_snaps:
        for it in s["snapshot"]["response"]["body"]["items"]:
            assert it["stack_code"] in by_code
            assert it["stack_code"].startswith("SYN-")

# 에피소드 하나를 골라내도 그 에피소드의 행이 완전하고 값이 곡선과 같음
def test_one_episode_is_complete(day_snaps, eps):
    ep = next(e for e in eps if e["day"] == D and e["start_slot"] + len(e["curve"]) <= 48)
    rows = [(s["slot"], it) for s in day_snaps
            for it in s["snapshot"]["response"]["body"]["items"]
            if it["stack_code"] == ep["stack_code"]]
    assert [slot for slot, _ in rows] == list(range(ep["start_slot"], ep["start_slot"] + len(ep["curve"])))
    field = f"{ep['item']}_mesure_value"
    for (slot, it), v in zip(rows, ep["curve"]):
        assert it[field] == snapshot.ratio_to_measure(v, ep["ref"]["perm_std"])[0]
    other = "sox" if ep["item"] == "nox" else "nox"
    assert all(it[f"{other}_mesure_value"] is None for _, it in rows)

# 스냅샷 원문 크기가 한도 안
def test_snapshot_size(day_snaps, config):
    limit = config["snapshot"]["max_message_bytes"]
    for s in day_snaps:
        size = len(json.dumps(s["snapshot"], ensure_ascii = False).encode("utf-8"))
        assert size < limit