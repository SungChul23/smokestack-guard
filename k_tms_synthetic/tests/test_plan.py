'''
- plan test: 설정에서 에피소드 계획표가 규칙대로 만들어지는지 확인
'''
import pytest
from synth import plan

# 테스트용 작은 설정 생성(입력: 시작 시각 -> 출력: config dict)
def sample_config(start = "2026-11-20 09:00"):
    return {
        "run": {"seed": 20261109, "start_kst": start},
        "episodes": {
            "S-01-E": 1, "S-02-E": 3, "S-03-E": 1, "S-04-E": 1, "S-05-E": 1, "S-06-E": 1, "S-07-E": 1, "S-08-E": 1, "S-09-E": 1,
        },
    }

# 에피소드는 11개, S-02는 항목별로 3개로 나뉨
def test_eleven_episodes_with_s02_variants():
    ids = [e["episode_id"] for e in plan.build_plan(sample_config())]
    assert len(ids) == 11
    assert "S-01-E" in ids
    assert {"S-02-E-NOX", "S-02-E-SOX", "S-02-E-NOXSOX"} <= set(ids)

# scenario_id는 "S-02"처럼 앞 두 조각이고, 항목은 변형에 맞음
def test_scenario_id_and_items():
    by_id = {e["episode_id"]: e for e in plan.build_plan(sample_config())}
    assert by_id["S-02-E-SOX"]["scenario_id"] == "S-02"
    assert by_id["S-02-E-SOX"]["items"] == ["sox"]
    assert by_id["S-02-E-NOXSOX"]["items"] == ["nox", "sox"]
    assert by_id["S-01-E"]["items"] == ["nox"]

# 합성 배출구 코드는 SYN-으로 시작, 에피소드 사이에 겹치지 않음
def test_stack_codes_start_with_syn_and_unique():
    codes = [c for e in plan.build_plan(sample_config()) for c in e["stack_codes"]]
    assert all(c.startswith("SYN-") for c in codes)
    assert len(codes) == len(set(codes))
    assert plan.make_stack_code("S-02-E-NOX", 1) == "SYN-S02ENOX-01"

# seed는 에피소드마다 다르고, 같은 설정이면 매번 같음
def test_seeds_unique_and_reproducible():
    a = [e["seed"] for e in plan.build_plan(sample_config())]
    b = [e["seed"] for e in plan.build_plan(sample_config())]
    assert a == b
    assert len(a) == len(set(a))

# 설정의 seed를 바꾸면 에피소드 seed도 바뀜
def test_seed_changes_with_base_seed():
    cfg = sample_config()
    cfg["run"]["seed"] = 1
    other = [e["seed"] for e in plan.build_plan(cfg)]
    base = [e["seed"] for e in plan.build_plan(sample_config())]
    assert other != base

# start_kst가 시각이 아니면 에러
def test_placeholder_start_time_is_rejected():
    with pytest.raises(ValueError):
        plan.build_plan(sample_config(start = "추후설정"))

# S-02-E가 3이 아니면 에러
def test_unexpected_count_is_rejected():
    cfg = sample_config()
    cfg["episodes"]["S-02-E"] = 2
    with pytest.raises(ValueError):
        plan.build_plan(cfg)