'''
- ingest_core test: 메시지 -> (경로, 파일 4개) 변환이 파일 모드 산출물과 같은지 Spark 없이 확인
'''
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from synth_train import generate, ingest_core, publish

D = date(2026, 11, 16)
EMPTY = b'{"response":{"header":{"resultCode":"0","totalCount":0,"resultMsg":"NORMAL_CODE"},"body":{"items":[]}}}'

@pytest.fixture(scope="module")
def out(config, ref_df, tmp_path_factory):
    path = tmp_path_factory.mktemp("ing")
    generate.generate_day(config, ref_df, D, path)
    return path

# 폴더 안 모든 파일을 {상대경로: 바이트}로
def tree(root) -> dict:
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

# 파일 모드 산출물과 경로·바이트가 같다
def test_same_bytes_as_file_mode(out):
    for m in publish.messages_from_dir(out):
        prefix, files = ingest_core.message_to_files(m["key"], m["value"], m["headers"])
        base = out / prefix
        assert base.is_dir()
        for name, data in files.items():
            assert (base / name).read_bytes() == data

# pool 모드와 시험 모드의 경로 템플릿
def test_path_templates():
    ts = datetime(2026, 11, 16, 16, 10, tzinfo=timezone.utc)
    train = publish.make_message(EMPTY, ts, {"generator_version": "g"}, "tms_synthetic_train")
    prefix, _ = ingest_core.message_to_files(train["key"], train["value"], train["headers"])
    assert prefix == "tms_synthetic_train/ingest_date=2026-11-16/hour=16/run_ts=20261116T161000Z"
    test = publish.make_message(EMPTY, ts, {"scenario_id": "S-01"}, "tms_synthetic", episode_id="S-01-E-NOX")
    prefix, _ = ingest_core.message_to_files(test["key"], test["value"], test["headers"])
    assert prefix == "tms_synthetic/episode=S-01-E-NOX/ingest_date=2026-11-16/hour=16/run_ts=20261116T161000Z"

# 실측 경로는 거부
def test_rejects_cleansys():
    ts = datetime(2026, 11, 16, 16, 10, tzinfo=timezone.utc)
    bad = publish.make_message(EMPTY, ts, {}, "tms_cleansys")
    with pytest.raises(ValueError):
        ingest_core.message_to_files(bad["key"], bad["value"], bad["headers"])

# 같은 메시지에는 같은 경로·바이트 (멱등)
def test_idempotent(out):
    m = publish.messages_from_dir(out)[5]
    a = ingest_core.message_to_files(m["key"], m["value"], m["headers"])
    b = ingest_core.message_to_files(m["key"], m["value"], m["headers"])
    assert a == b

# 메시지 목록을 파일로 쓰면 파일 모드 산출물과 바이트까지 같고, 다시 써도 같다
def test_write_messages_equals_file_mode(out, tmp_path):
    msgs = publish.messages_from_dir(out)
    assert ingest_core.write_messages(msgs, tmp_path) == 48
    assert tree(tmp_path / "tms_synthetic_train") == tree(out / "tms_synthetic_train")
    ingest_core.write_messages(msgs, tmp_path)                    # 한 번 더 (멱등)
    assert tree(tmp_path / "tms_synthetic_train") == tree(out / "tms_synthetic_train")

# 메시지 순서가 뒤섞여 들어와도 결과가 같다 (Kafka에서 읽은 순서에 의존하지 않음)
def test_write_messages_order_independent(out, tmp_path):
    msgs = publish.messages_from_dir(out)
    ingest_core.write_messages(list(reversed(msgs)), tmp_path)
    assert tree(tmp_path / "tms_synthetic_train") == tree(out / "tms_synthetic_train")