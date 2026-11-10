'''
- writer test: 파일을 디스크에 쓰는 규칙 확인
'''
import gzip
import hashlib
import json
import pytest
from datetime import datetime, timezone
from synth import snapshot, writer
from tests.test_snapshot import sample_item

RUN_TS = datetime(2026, 11, 20, 0, 0, tzinfo = timezone.utc)

# 샘플 snapshot으로 4개 파일 묶음 생성
def make_sample_files():
    snap = snapshot.make_snapshot([sample_item()])
    return snapshot.make_files(snap, "S-01-E", RUN_TS, {"scenario_id": "S-01"})

# 테스트용 정상 경로
def prefix_of():
    return snapshot.build_prefix("S-01-E", RUN_TS)

# 정상 입력이라면 4개 파일이 경로에 모두 생성
def test_writes_all_four_files(tmp_path):
    writer.write_files(tmp_path, prefix_of(), make_sample_files())
    names = sorted(p.name for p in (tmp_path / prefix_of()).iterdir())
    assert names == ["_SUCCESS", "manifest.json", "snapshot.json.gz", "snapshot.meta.json"]

@pytest.mark.parametrize("bad", [
    "tms_cleansys/ingest_date=2026-11-20/hour=00/run_ts=X",     # 실측 경로
    "other/ingest_date=2026-11-20",                             # 엉뚱한 경로
    "tms_synthetic/../tms_cleansys/x",                          # 거슬러 올라가는 경로
    "/tms_synthetic/x",                                         # 절대 경로
])
# 합성 경로가 아니면 거부 후 아무 파일도 쓰지 않음
def test_rejects_bad_prefix(tmp_path, bad):
    with pytest.raises(ValueError):
        writer.write_files(tmp_path, bad, make_sample_files())
    assert list(tmp_path.iterdir()) == []

# 디스크에서 다시 읽은 해시가 meta sha256_raw와 같다
def test_written_bytes_match_meta_hash(tmp_path):
    writer.write_files(tmp_path, prefix_of(), make_sample_files())
    base = tmp_path / prefix_of()
    raw = gzip.decompress((base / "snapshot.json.gz").read_bytes())
    meta = json.loads((base / "snapshot.meta.json").read_text(encoding = "utf-8"))
    assert hashlib.sha256(raw).hexdigest() == meta["sha256_raw"]

# 해시가 meta와 다르면 에러 후 manifest, _SUCCESS를 작성하지 않음
def test_currupted_data_stops_before_commit(tmp_path):
    files = make_sample_files()
    files["snapshot.json.gz"] = gzip.compress(b"{}", mtime = 0)
    with pytest.raises(ValueError):
        writer.write_files(tmp_path, prefix_of(), files)
    base = tmp_path / prefix_of()
    assert not (base / "_SUCCESS").exists()
    assert not (base / "manifest.json").exists()

# S-07 (결함 에피소드 (commit = False))면 데이터 파일만 쓰고 확정 표지는 쓰지 않음
def test_commit_false_skips_success(tmp_path):
    writer.write_files(tmp_path, prefix_of(), make_sample_files(), commit = False)
    base = tmp_path / prefix_of() 
    assert (base / "snapshot.json.gz").exists()
    assert not (base / "_SUCCESS").exists()

# 똑같은 입력으로 두 번 쓰면 모든 파일의 바이트가 같아야 함(재현성)
def test_same_input_same_bytes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    writer.write_files(a, prefix_of(), make_sample_files())
    writer.write_files(b, prefix_of(), make_sample_files())
    for name in ["snapshot.json.gz", "snapshot.meta.json", "manifest.json", "_SUCCESS"]:
        assert (a / prefix_of() / name).read_bytes() == (b / prefix_of() / name).read_bytes()