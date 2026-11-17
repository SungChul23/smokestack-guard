'''
- plan test: 설정에서 에피소드 계획표가 규칙대로 만들어지는지 확인
'''
import pytest
from synth import plan

# 테스트용 시나리오 설정. 실제 config.yaml의 episodes와 같은 구조(21개 에피소드)
def sample_episodes():
    return {
        "S-01-E": {"items": ["nox", "sox"]},
        "S-02-E": {"episodes": [
            {"suffix": "NOX", "items": ["nox"]},
            {"suffix": "SOX", "items": ["sox"]},
            {"suffix": "NOXSOX-NOXUP", "items": ["nox", "sox"], "rising": ["nox"]},
            {"suffix": "NOXSOX-SOXUP", "items": ["nox", "sox"], "rising": ["sox"]},
        ]},
        "S-03-E": {"variants": ["OVER", "UNDER"], "items": ["nox", "sox"]},
        "S-04-E": {"variants": ["EXCEED", "SPIKE", "PLATEAU"], "items": ["nox", "sox"]},
        "S-05-E": {"items": ["nox"]},
        "S-06-E": {"items": ["nox"]},
        "S-07-E": {"variants": ["SAME", "CONFLICT"], "items": ["nox"]},
        "S-08-E": {"items": ["nox"]},
    }

# 테스트용 설정 생성(입력: 시작 시각 -> 출력: config dict)
def sample_config(start = "2026-11-20 09:00"):
    return {"run": {"seed": 20261109, "start_kst": start}, "episodes": sample_episodes()}

# 에피소드ID -> seed 딕셔너리 (seed 비교용 도우미)
def seeds_of(cfg):
    return {e["episode_id"]: e["seed"] for e in plan.build_plan(cfg)}

# 에피소드는 21개이고 ID가 겹치지 않음
def test_twenty_one_episodes():
    ids = [e["episode_id"] for e in plan.build_plan(sample_config())]
    assert len(ids) == 21
    assert len(ids) == len(set(ids))

# 변형 × 성분으로 펼쳐지고, 성분이 하나뿐인 시나리오는 성분 접미사가 붙지 않음
def test_episode_ids():
    ids = {e["episode_id"] for e in plan.build_plan(sample_config())}
    expected = {
        "S-01-E-NOX", "S-01-E-SOX",
        "S-02-E-NOX", "S-02-E-SOX", "S-02-E-NOXSOX-NOXUP", "S-02-E-NOXSOX-SOXUP",
        "S-03-E-OVER-NOX", "S-03-E-OVER-SOX", "S-03-E-UNDER-NOX", "S-03-E-UNDER-SOX",
        "S-04-E-EXCEED-NOX", "S-04-E-SPIKE-SOX", "S-04-E-PLATEAU-NOX",
        "S-05-E", "S-06-E", "S-07-E-SAME", "S-07-E-CONFLICT", "S-08-E",
    }
    assert expected <= ids

# 시나리오, 변형, 성분, 오르는 성분이 맞게 들어감
def test_scenario_variant_items_rising():
    by_id = {e["episode_id"]: e for e in plan.build_plan(sample_config())}
    e = by_id["S-03-E-UNDER-SOX"]
    assert (e["scenario_id"], e["variant"], e["items"], e["rising"]) == ("S-03", "UNDER", ["sox"], ["sox"])
    e = by_id["S-02-E-NOXSOX-SOXUP"]
    assert (e["scenario_id"], e["variant"]) == ("S-02", None)
    assert e["items"] == ["nox", "sox"] and e["rising"] == ["sox"]
    assert by_id["S-02-E-NOX"]["rising"] == ["nox"]          # rising을 안 적으면 items 전체가 오름
    assert by_id["S-05-E"]["variant"] is None

# 합성 배출구 코드는 SYN-으로 시작하고 에피소드 사이에 겹치지 않음
def test_stack_codes_start_with_syn_and_unique():
    codes = [c for e in plan.build_plan(sample_config()) for c in e["stack_codes"]]
    assert all(c.startswith("SYN-") for c in codes)
    assert len(codes) == len(set(codes))
    assert plan.make_stack_code("S-02-E-NOXSOX-NOXUP", 1) == "SYN-S02ENOXSOXNOXUP-01"

# seed는 에피소드마다 다르고, 같은 설정이면 매번 같음
def test_seeds_unique_and_reproducible():
    a, b = seeds_of(sample_config()), seeds_of(sample_config())
    assert a == b
    assert len(set(a.values())) == len(a)

# 에피소드 하나를 설정에서 빼도 나머지 에피소드의 seed는 그대로
def test_seed_not_shifted_by_removing_episode():
    cfg = sample_config()
    full = seeds_of(cfg)
    del cfg["episodes"]["S-01-E"]
    part = seeds_of(cfg)
    assert all(part[k] == full[k] for k in part)

# 설정의 seed를 바꾸면 에피소드 seed도 바뀜
def test_seed_changes_with_base_seed():
    cfg = sample_config()
    cfg["run"]["seed"] = 1
    assert seeds_of(cfg) != seeds_of(sample_config())

# start_kst가 시각이 아니면 에러
def test_placeholder_start_time_is_rejected():
    with pytest.raises(ValueError):
        plan.build_plan(sample_config(start = "추후설정"))

# 모르는 성분 이름이면 에러
def test_unknown_item_is_rejected():
    cfg = sample_config()
    cfg["episodes"]["S-05-E"] = {"items": ["tsp"]}
    with pytest.raises(ValueError):
        plan.build_plan(cfg)

# rising이 items 안에 없는 성분이면 에러
def test_rising_must_be_subset_of_items():
    cfg = sample_config()
    cfg["episodes"]["S-02-E"]["episodes"][0]["rising"] = ["sox"]     # 이 에피소드의 items는 [nox]
    with pytest.raises(ValueError):
        plan.build_plan(cfg)

# 같은 에피소드 ID가 두 번 만들어지면 에러
def test_duplicate_episode_ids_are_rejected():
    cfg = sample_config()
    cfg["episodes"]["S-03-E"]["variants"] = ["OVER", "OVER"]
    with pytest.raises(ValueError):
        plan.build_plan(cfg)