'''
- snapshot 만들기 test
- 확인하는 것
    - 항목이 실제 API 항목과 똑같은 18개 필드, 문자열 타입인지
    - 응답 모양이 실제와 같은지
    - 저장 폴더 경로가 약속한 형식인지
    - 압축 원문 / 메타 / 확정 표지 4개 파일이 서로 맞는지
    - 같은 입력이면 파일 내용이 똑같은지
'''
import gzip
import hashlib
import json
import pytest
from datetime import datetime, timezone
from synth import snapshot

# 실행 시각(UTC)
RUN_TS = datetime(2026, 11, 20, 0, 10, tzinfo = timezone.utc)
INFO = {"scenario_id": "S-01-E", "generator_version": "gen-v1", "stats_version": "provisional"}

# 실제 API 항목의 18개 필드 이름
REAL_FIELDS = {"area_nm", "fact_manage_nm", "stack_code", "mesure_dt"} | {
    f"{name}_{kind}"
    for name in ["nox", "sox", "tsp", "hcl", "co", "nh3", "hf"]
    for kind in ["mesure_value", "exhst_perm_stdr_value"]
}

# 테스트용 항복: NOX만 측정하는 굴뚝이 62.4%를 기록한 상황 (허용기준 100)
def sample_item():
    return snapshot.make_item(
        "울산광역시",       
        "합성사업장-S01E-01", 
        "SYN-S01E-01", "2026-11-20 09:00", 
        {"nox": snapshot.ratio_to_measure(62.4, 100)},
    )

# 측정값은 소수 둘째 자리 문자열, 허용 기준을 필요한 만큼만
def test_ratio_to_measure():
    assert snapshot.ratio_to_measure(62.4, 100) == ("62.40", "100")
    assert snapshot.ratio_to_measure(50, 9.8) == ("4.90", "9.8")

# 실제 필드와 똑같이 18개의 필드
def test_item_has_exactly_the_real_field():
    item = sample_item()
    assert set(item) == REAL_FIELDS
    assert len(item) == 18

# 모든 값은 문자열이거나 null. 
def test_item_value_types():
    for value in sample_item().values():
        assert value is None or isinstance(value, str)

# 측정하지 않는 항목은 null, 측정한 항목만 값이 있음
def test_unmeasured_items_are_none():
    item = sample_item()
    assert item["nox_mesure_value"] == "62.40"
    assert item["nox_exhst_perm_stdr_value"] == '100'
    assert item["sox_mesure_value"] is None
    assert item["sox_exhst_perm_stdr_value"] is None

# 모르는 항목 이름은 넘어가지 않고 에러 발생
def test_unknown_item_raise():
    with pytest.raises(ValueError):
        snapshot.make_item("a", "b", "c", "2026-11-20 09:00", {"nxo": ("1.00", "100")})

# API 응답 모양: header(결과 코드 0, 전체 건수) + body(item)
def test_snapshot_shape():
    snap = snapshot.make_snapshot([sample_item(), sample_item()])
    header = snap["response"]["header"]
    assert header == {"resultCode": "0", "totalCount": 2, "resultMsg": "NORMAL_CODE"}
    assert list(snap["response"]["body"]) == ["items"]
    assert len(snap["response"]["body"]["items"]) == 2

# 저장 폴더 경로가 약속한 양식
def test_prefix_format():
    assert snapshot.build_prefix("S-01-E", RUN_TS) == ("tms_synthetic/episode=S-01-E/ingest_date=2026-11-20/hour=00/run_ts=20261120T001000Z")

# 시간대가 없는 시각은 에러 
def test_prefix_requires_timezone():
    with pytest.raises(ValueError):
        snapshot.build_prefix("S-01-E", datetime(2026, 11, 20, 0, 10))

# 생성되는 파일은 4개(원문, 메타, manifest, _SUCCESS)
def test_files_are_complete():
    files = snapshot.make_files(snapshot.make_snapshot([sample_item()]), "S-01-E", RUN_TS, INFO)
    assert set(files) == {"snapshot.json.gz", "snapshot.meta.json", "manifest.json", "_SUCCESS"}
    assert files["_SUCCESS"] == b""

# 압축 해제 시 원래 snapshot이 그대로 나오고, 메타의 해시, 점검 결과가 맞아야 함
def test_raw_roundtrip_and_meta():
    snap = snapshot.make_snapshot([sample_item()])
    files = snapshot.make_files(snap, "S-01-E", RUN_TS, INFO)
    
    raw = gzip.decompress(files["snapshot.json.gz"])
    assert json.loads(raw) == snap

    meta = json.loads(files["snapshot.meta.json"])
    assert meta["sha256_raw"] == hashlib.sha256(raw).hexdigest()
    assert meta["inspect"]["ok"] is True
    assert meta["inspect"]["total_count"] == meta["inspect"]["item_count"] == 1
    assert meta["synthetic"]["episode_id"] == "S-01-E"
    assert meta["synthetic"]["scenario_id"] == "S-01-E"

# manifest에 적힌 파일 크기, 해시가 실제 파일과 동일
def test_manifest_matches_files():
    files = snapshot.make_files(snapshot.make_snapshot([sample_item()]), "S-01-E", RUN_TS, INFO)
    manifest = json.loads(files["manifest.json"])
    for entry in manifest["files"]:
        data = files[entry["name"]]
        assert entry["bytes"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()

# 같은 입력으로 재생성 시 모든 파일이 바이트까지 같아야 함
def test_files_are_deterministic():
    snap = snapshot.make_snapshot([sample_item()])
    a = snapshot.make_files(snap, "S-01-E", RUN_TS, INFO)
    b = snapshot.make_files(snap, "S-01-E", RUN_TS, INFO)
    assert a == b

# 응답 점검에 실패한 snapshot에는 확정 표지를 만들지 않음
def test_commit_refused_when_inspect_fails():
    snap = snapshot.make_snapshot([sample_item()])
    snap["response"]["header"]["totalCount"] = 3
    data = snapshot.make_data_files(snap, "S-07-E", RUN_TS, INFO)
    with pytest.raises(ValueError):
        snapshot.make_commit_files(data, RUN_TS)