'''
- generate test: 설정 -> 파일 생성까지 전체 흐름이 규칙대로 동작하는지 확인.
'''
import json
from pathlib import Path
from synth import generate

FIXTURE = Path(__file__).parent / "fixtures" / "ref_stats_sample.csv"

# 테스트용 설정. 입력: 없음 -> 출력: dict (S-01 하나, 측정 4칸 = snapshot 12개)
def sample_config():
    return {
        "run": {
            "seed": 1, "generator_version": "gen-v1", "stats_version": "provisional",
            "snapshot_interval_min": 10, "slot_min": 30, "episode_steps": 4,
            "start_kst": "2026-11-20 09:00",
        },
        "ref_selection": {
            "min_valid": 200,
            "normal": {"mean": [10, 50], "phi": [0.5, 0.95], "p99_max": 80},
        },
        "episodes": {"S-01-E": {"items": ["nox"]}}, 
    }

# 측정이 4칸이면 snapshot이 12개가 만들어지고, 모두 _SUCCESS가 있어야 함.
def test_creates_snapshot_folders_with_success(tmp_path):
    generate.generate(sample_config(), FIXTURE, tmp_path)
    done = list((tmp_path / "tms_synthetic" / "episode=S-01-E").glob("*/*/*/_SUCCESS"))
    assert len(done) == 12

# out 바로 아래에는 tms_synthetic 폴더와 manifest.jsonl만 있어야 함
def test_writes_only_synthetic_and_manifest(tmp_path):
    generate.generate(sample_config(), FIXTURE, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifest.jsonl", "tms_synthetic"]

# manifest.jsonl 한 줄에 에피소드 정보가 알맞게 담김
def test_manifest(tmp_path):
    generate.generate(sample_config(), FIXTURE, tmp_path)
    lines = (tmp_path / "manifest.jsonl").read_text(encoding = "utf-8").splitlines()
    row = json.loads(lines[0])
    assert len(lines) == 1
    assert row["episode_id"] == "S-01-E" and row["snapshots"] == 12
    assert row["stack_codes"][0].startswith("SYN-")
    assert row["first_mesure_dt"] == "2026-11-20 09:00"
    assert row["last_mesure_dt"] == "2026-11-20 10:30"

# 아직 구현 전이 시나리오는 에러 없이 건너뜀
def test_unimplemented_scenarios_are_skipped(tmp_path):
    cfg = sample_config()
    cfg["episodes"]["S-03-E"] = {"variants": ["OVER"], "items": ["nox"]}       # 에피소드 ID: S-03-E-OVER
    generate.generate(cfg, FIXTURE, tmp_path)
    assert not (tmp_path / "tms_synthetic" / "episode=S-03-E-OVER").exists()

# 같은 설정으로 두 번 만들면 모든 파일의 바이트가 같음
def test_same_config_same_bytes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate.generate(sample_config(), FIXTURE, a)
    generate.generate(sample_config(), FIXTURE, b)
    files_a = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    assert files_a == files_b
    for rel in files_a:
        assert (a / rel).read_bytes() == (b / rel).read_bytes()

# 배경 상한(hi)은 설정의 참조 조건(p99_max)과 같아야 함 (S-01은 70%)
def test_background_cap_follows_config(tmp_path, monkeypatch):
    seen = {}
    real = generate.episode.normal_series                      # 원래 함수를 보관

    def spy(*args, **kwargs):                                  # 인자를 기록한 뒤 원래 함수를 그대로 실행
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(generate.episode, "normal_series", spy)
    cfg = sample_config()
    cfg["ref_selection"]["normal"]["p99_max"] = 70
    generate.generate(cfg, FIXTURE, tmp_path)
    assert seen["hi"] == 70