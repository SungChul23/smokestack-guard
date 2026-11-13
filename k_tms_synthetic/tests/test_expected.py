'''
- expected test: 손으로 쓰는 expected/*.yaml이 형식에 맞는지 확인 (오타·빠진 항목 방지)
'''
import yaml
from pathlib import Path

EXPECTED_DIR = Path(__file__).parent.parent / "expected"
REQUIRED = {"episode_id", "scenario_id", "items", "rising", "steps",
            "trajectory_pct", "silver_expect", "label_expect", "known_mismatch"}

# expected/ 아래 모든 yaml을 읽어 {파일이름(확장자 제외): 내용} 딕셔너리로
def load_all():
    return {p.stem: yaml.safe_load(p.read_text(encoding = "utf-8")) for p in sorted(EXPECTED_DIR.glob("*.yaml"))}

# S-01 두 에피소드의 expected가 있어야 함 (시나리오를 구현할 때마다 여기에 이름을 추가)
def test_expected_files_exist():
    assert {"S-01-E-NOX", "S-01-E-SOX", "S-02-E-NOX", "S-02-E-SOX",
        "S-02-E-NOXSOX-NOXUP", "S-02-E-NOXSOX-SOXUP",
        "S-03-E-OVER-NOX", "S-03-E-UNDER-NOX", "S-03-E-OVER-SOX", "S-03-E-UNDER-SOX",
        "S-04-E-EXCEED-NOX", "S-04-E-SPIKE-NOX", "S-04-E-PLATEAU-NOX"} <= set(load_all())

# 필수 키가 모두 있음
def test_required_keys():
    for name, d in load_all().items():
        assert REQUIRED <= set(d), f"{name}: 빠진 키 {REQUIRED - set(d)}"

# 파일 이름 = episode_id, 시나리오 번호 = 이름 앞 두 조각
def test_name_matches_ids():
    for name, d in load_all().items():
        assert d["episode_id"] == name
        assert d["scenario_id"] == "-".join(name.split("-")[:2])

# 성분이 nox·sox 중에 있고, rising은 items 안에 있음
def test_items_and_rising():
    for name, d in load_all().items():
        assert set(d["items"]) <= {"nox", "sox"}, name
        assert set(d["rising"]) <= set(d["items"]), name

# silver_expect와 label_expect에 성분마다 항목이 있고, 라벨 건수의 합이 steps와 같음
def test_per_item_sections_and_label_sum():
    for name, d in load_all().items():
        for item in d["items"]:
            assert item in d["silver_expect"], f"{name}: silver_expect에 {item} 없음"
            le = d["label_expect"][item]
            assert le["positive"] + le["negative"] + le["excluded"] == d["steps"], f"{name}: {item} 라벨 합이 steps와 다름"

# 고정 궤적에 정확히 90.00인 값을 쓰지 않음 (저장 때 반올림으로 0.8999…가 될 수 있음)
def test_trajectory_avoids_exact_90():
    for name, d in load_all().items():
        if d["trajectory_pct"]:
            assert all(v != 90 for v in d["trajectory_pct"]), name

# 고정 궤적이 있으면 시작 칸·단계 목록이 있고, 단계 수가 값 수와 같고, 궤적이 에피소드 안에 들어감
def test_trajectory_keys():
    for name, d in load_all().items():
        if d["trajectory_pct"]:
            assert "trajectory_start_step" in d, f"{name}: trajectory_start_step 없음"
            assert len(d["trajectory_stage"]) == len(d["trajectory_pct"]), f"{name}: 단계 수가 값 수와 다름"
            start, n = d["trajectory_start_step"], len(d["trajectory_pct"])
            assert 1 <= start and start + n - 1 <= d["steps"], f"{name}: 궤적이 에피소드 밖으로 나감"

# 궤적이 있는 에피소드에서 trajectory_ratio_tol은 rising 성분에만 있어야 함
def test_trajectory_check_only_on_rising_items():
    for name, d in load_all().items():
        if not d["trajectory_pct"]:
            continue
        for item in d["items"]:
            has_check = "trajectory_ratio_tol" in d["silver_expect"][item]
            assert has_check == (item in d["rising"]), f"{name}: {item}의 궤적 검사 키가 rising과 맞지 않음"