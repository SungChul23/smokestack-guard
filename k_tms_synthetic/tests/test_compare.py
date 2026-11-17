'''
- compare test: 생성 결과를 expected와 대조해 어긋남을 잡아내는지 확인
'''
import yaml
from synth import generate, compare, validate
from tests.test_generate import FIXTURE
from tests.test_generate_trajectory import traj_config

# 테스트용 정상 결과: S-04 SPIKE(NOX 단독) 에피소드 하나
def make_spike(tmp_path):
    cfg = traj_config({"S-04-E": {"variants": ["SPIKE"], "items": ["nox"]}}, {"S-04-SPIKE": [59, 61, 94, 63, 60]})
    generate.generate(cfg, FIXTURE, tmp_path)
    return tmp_path

# 알맞은 expected (dict). 인자로 일부를 덮어쓸 수 있음
def spike_expected(**spec):
    nox = {"rows": 96, "status": "ok", "trajectory_ratio_tol": 0.005, "ratio_max_exclusive_outside": 0.90}
    nox.update(spec)
    return {"episode_id": "S-04-E-SPIKE", "scenario_id": "S-04", "items": ["nox"], "rising": ["nox"], "steps": 96,
            "trajectory_start_step": 48, "trajectory_pct": [59, 61, 94, 63, 60], "silver_expect": {"nox": nox}}

# 걸린 검사 이름 집합
def checks_of(issues):
    return {i["check"] for i in issues}

# 알맞은 expected면 문제 없음
def test_matching_expected_passes(tmp_path):
    out = make_spike(tmp_path)
    assert compare.compare_episode(out, spike_expected()) == []

# 행 수가 다르면 rows
def test_detects_row_count_mismatch(tmp_path):
    out = make_spike(tmp_path)
    assert "rows" in checks_of(compare.compare_episode(out, spike_expected(rows = 95)))

# 궤적 값이 다르면 trajectory
def test_detects_trajectory_mismatch(tmp_path):
    out = make_spike(tmp_path)
    exp = spike_expected()
    exp["trajectory_pct"] = [59, 61, 99, 63, 60]
    assert "trajectory" in checks_of(compare.compare_episode(out, exp))

# 궤적 밖 상한을 일부러 낮게 적으면 outside
def test_detects_outside_limit_violation(tmp_path):
    out = make_spike(tmp_path)
    assert "outside" in checks_of(compare.compare_episode(out, spike_expected(ratio_max_exclusive_outside = 0.01)))

# 궤적 앞 구간 상한을 어기면 lead_in
def test_detects_lead_in_violation(tmp_path):
    out = make_spike(tmp_path)
    assert "lead_in" in checks_of(compare.compare_episode(out, spike_expected(lead_in_max_exclusive = 0.01)))

# expected 파일이 없으면 expected 문제
def test_missing_expected_file_is_reported(tmp_path):
    out = make_spike(tmp_path / "out")
    empty = tmp_path / "expected"
    empty.mkdir()
    assert "expected" in checks_of(compare.compare_all(out, empty))

# 파일로 저장된 expected를 읽어 대조까지 이어지고, validate_out에도 연결됨
def test_validate_out_with_expected_dir(tmp_path):
    out = make_spike(tmp_path / "out")
    exp_dir = tmp_path / "expected"
    exp_dir.mkdir()
    (exp_dir / "S-04-E-SPIKE.yaml").write_text(yaml.safe_dump(spike_expected()), encoding = "utf-8")
    assert validate.validate_out(out, exp_dir) == []
    (exp_dir / "S-04-E-SPIKE.yaml").write_text(yaml.safe_dump(spike_expected(rows = 1)), encoding = "utf-8")
    assert "rows" in checks_of(validate.validate_out(out, exp_dir))