'''
- generate test: 하루 생성의 폴더 구조, manifest, 바이트 동일, 날짜 순서 무관, 시간대 분포 확인
'''
import json
from datetime import date
from pathlib import Path
from synth_train import daily, generate

D1 = date(2026, 11, 16)
D2 = date(2026, 11, 17)

# 폴더 안 모든 파일을 상대경로: 바이트 로
def tree(root) -> dict:
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

# 폴더 구조: 스냅샷 48개, 폴더마다 파일 4개, 에피소드 폴더 없음
def test_folder_structure(config, ref_df, tmp_path):
    generate.generate_day(config, ref_df, D1, tmp_path)
    run_dirs = [p for p in (tmp_path / "tms_synthetic_train").rglob("run_ts=*") if p.is_dir()]
    assert len(run_dirs) == 48
    for d in run_dirs:
        assert sorted(f.name for f in d.iterdir()) == [
            "_SUCCESS", "manifest.json", "snapshot.json.gz", "snapshot.meta.json"
        ]
    assert not list((tmp_path / "tms_synthetic_train").rglob("episode=*"))

# manifest: 시작 날짜가 그날인 에피소드만, 필수 필드 존재
def test_manifest_fields(config, ref_df, tmp_path):
    generate.generate_day(config, ref_df, D1, tmp_path)
    lines = (tmp_path / "manifest" / "2026-11-16.jsonl").read_text(encoding = "utf-8").splitlines()
    rows = [json.loads(x) for x in lines]
    want = sum(n for shapes in config["daily_episodes"].values() for n in shapes.values())
    assert len(rows) == want
    need = {"day", "item", "shape", "n", "stack_code", "ref", "seed", "start_slot",
            "first_mesure_dt", "last_mesure_dt", "snapshots", "rows",
            "stats_version", "generator_version"}
    for r in rows:
        assert need <= set(r)
        assert r["day"] == "2026-11-16"
        assert r["stack_code"].startswith("SYN-T-20261116-")
        assert r["snapshots"] == r["rows"]

# 같은 날짜를 두 번 만들면 바이트가 같음
def test_same_day_same_bytes(config, ref_df, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate.generate_day(config, ref_df, D1, a)
    generate.generate_day(config, ref_df, D1, b)
    assert tree(a) == tree(b)

# 두 날짜를 어떤 순서로 만들어도 결과가 같음
def test_day_order_independent(config, ref_df, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate.backfill(config, ref_df, D1, D2, a)
    generate.generate_day(config, ref_df, D2, b)
    generate.generate_day(config, ref_df, D1, b)
    assert tree(a) == tree(b)

# 사건이 24시간 시간대에 걸쳐 분포
def test_events_spread_over_hours(config, ref_df):
    hours = set()
    for e in daily.episodes_started_on(config, ref_df, D1):
        first_high = next(i for i, v in enumerate(e["curve"]) if v >= 90)
        hours.add(((e["start_slot"] + first_high) % 48) // 2)
    assert len(hours) >= 20