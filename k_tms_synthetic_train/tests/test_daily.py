'''
- daily test: 하루에 시작하는 에피소드 수, seed 고정, 자정 결침 확인
'''
from collections import Counter
from datetime import date
from synth_train import daily, snapshot
import numpy as np

D = date(2026, 11, 16)

# 성분 x 모양 별 에피소드 수가 설정과 같고, 시작 슬롯이 하루에 펴짐
def test_episode_counts(config, ref_df):
    eps = daily.episodes_started_on(config, ref_df, D)
    got = Counter((e["item"], e["shape"]) for e in eps)
    want = {(item, shape): n
            for item, shapes in config["daily_episodes"].items()
            for shape, n in shapes.items()}
    assert got == want
    nox_slots = {e["start_slot"] for e in eps if e["item"] == "nox"}
    assert all(0 <= s < 48 for s in nox_slots)
    assert len(nox_slots) >= 40

# 같은 입력이면 같은 에피소드 , 다른 날짜와 서로 영향이 없음
def test_seed_is_deterministic(config, ref_df):
    a = daily.episodes_started_on(config, ref_df, D)
    daily.episodes_started_on(config, ref_df, date(2026, 11, 17))
    b = daily.episodes_started_on(config, ref_df, D)
    assert [e["seed"] for e in a] == [e["seed"] for e in b]
    assert [e["stack_code"] for e in a] == [e["stack_code"] for e in b]
    assert [e["start_slot"] for e in a] == [e["start_slot"] for e in b]
    assert [e["ref"]["stack_code"] for e in a] == [e["ref"]["stack_code"] for e in b]
    assert all(np.array_equal(x["curve"], y["curve"]) for x, y in zip(a, b))
    other = daily.episodes_started_on(config, ref_df, date(2026, 11, 17))
    assert {e["seed"] for e in a}.isdisjoint({e["seed"] for e in other})

def test_stack_code_format(config, ref_df):
    e = daily.episodes_started_on(config, ref_df, D)[0]
    assert e["stack_code"].startswith("SYN-T-20261116-")
    assert e["stack_code"].count("-") == 5

# 에피소드가 하루 안에 들어오는 길이인지 확인
def test_episode_shorter_than_a_day(config, ref_df):
    assert all(len(e["curve"]) < 48 for e in daily.episodes_started_on(config, ref_df, D))

# 자정을 걸친 에피소드를 두 날로 나누어 이으면 한 번에 만든 곡선과 같음
def test_midnight_spill(config, ref_df):
    prev = date(2026, 11, 15)
    eps = [e for e in daily.episodes_started_on(config, ref_df, prev)
           if e["start_slot"] + len(e["curve"]) > 48]
    assert eps
    for e in eps:
        first = daily.slots_on(e, prev)
        second = daily.slots_on(e, D)
        assert [s for s, _ in second][0] == 0
        joined = [v for _, v in first] + [v for _, v in second]
        assert joined == [float(v) for v in e["curve"]]

# 곡선 값이 파일에 쓰일 문자열에서 되돌린 비율과 정확히 같음
def test_curve_matches_emitted_strings(config, ref_df):
    for e in daily.episodes_started_on(config, ref_df, D):
        p = e["ref"]["perm_std"]
        for v in e["curve"]:
            s, lim = snapshot.ratio_to_measure(v, p)
            assert float(s) / float(lim) * 100 == v