"""ktms_pipeline 단위 테스트 (Spark 없음). spec 008 FR-002·003·005, research R6·R9."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from ktms_cases import build_silver
from smokestack_guard.silver.ml_ready import COLUMNS, to_ml_ready

from ktms_pipeline import (
    DayRange,
    check_source_prefix,
    failure_record,
    in_range,
    ingest_dates,
    ml_ready_window,
    resolve_range,
    run_record_key,
    table_location,
    write_run_record,
)

RUN_AT = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)  # KST 11-13 03:00


# ---------------------------------------------------------------------------
# 처리 범위 (T005)
# ---------------------------------------------------------------------------


def test_auto_is_last_two_complete_days():
    assert resolve_range("auto", "auto", now=RUN_AT) == DayRange(
        date(2026, 11, 11), date(2026, 11, 12)
    )


def test_auto_just_before_kst_midnight():
    r = resolve_range("auto", "auto", now=datetime(2026, 11, 12, 14, 59, tzinfo=UTC))
    assert r.end == date(2026, 11, 11)


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("auto", "2026-11-10", "둘 다"),
        ("2026-11-10", "auto", "둘 다"),
        ("2026-11-10", "2026-11-09", "늦다"),
        ("2026-11-12", "2026-11-13", "끝난 날짜"),  # 오늘(KST 11-13)은 진행 중
        ("2026/11/10", "2026-11-10", "YYYY-MM-DD"),
    ],
)
def test_invalid_ranges(start, end, message):
    with pytest.raises(ValueError, match=message):
        resolve_range(start, end, now=RUN_AT)


def test_max_days():
    with pytest.raises(ValueError, match="7일까지"):
        resolve_range("2026-11-01", "2026-11-08", now=RUN_AT, max_days=7)
    assert resolve_range("2026-11-01", "2026-11-07", now=RUN_AT, max_days=7).days == 7
    assert resolve_range("2026-10-30", "2026-11-12", now=RUN_AT).days == 14


def test_ingest_dates_daily_and_past():
    assert ingest_dates(DayRange(date(2026, 11, 11), date(2026, 11, 12)), now=RUN_AT) == (
        date(2026, 11, 10),
        date(2026, 11, 12),
    )
    assert ingest_dates(DayRange(date(2026, 11, 1), date(2026, 11, 3)), now=RUN_AT) == (
        date(2026, 10, 31),
        date(2026, 11, 4),
    )


def test_ml_ready_window_inclusive_bounds():
    lo, hi = ml_ready_window(DayRange(date(2026, 11, 11), date(2026, 11, 12)))
    assert (lo, hi) == (datetime(2026, 11, 10, 21, 30), datetime(2026, 11, 13, 0, 30))


def test_table_location():
    assert table_location("b", "tms_silver2.ktms") == "s3://b/silver2/ktms"
    assert table_location("b", "tms_silver2.ktms_ml_ready") == "s3://b/silver2/ktms_ml_ready"


# ---------------------------------------------------------------------------
# 원본 경로 검사 (T007, US5)
# ---------------------------------------------------------------------------


def test_default_prefix_passes():
    check_source_prefix("tms_cleansys/")


def test_other_prefix_needs_c_prefix_argument():
    def read_bronze(bucket, start=None, end=None, s3=None):  # 지금의 C 함수 모양
        return None

    with pytest.raises(ValueError, match="C의 read_bronze에 경로 인자 필요"):
        check_source_prefix("tms_synthetic/", read_bronze=read_bronze)


def test_other_prefix_passes_when_c_adds_argument():
    def read_bronze(bucket, start=None, end=None, s3=None, prefix="tms_cleansys/"):
        return None

    check_source_prefix("tms_synthetic/", read_bronze=read_bronze)


def test_current_c_read_bronze_rejects_synthetic():
    with pytest.raises(ValueError, match="경로 인자 필요"):
        check_source_prefix("tms_synthetic/")


# ---------------------------------------------------------------------------
# 실행 기록
# ---------------------------------------------------------------------------


def test_run_record_key_and_local_write(tmp_path):
    key = run_record_key("silver2/_runs/ktms/", RUN_AT, "jr_1")
    assert key == "silver2/_runs/ktms/20261112T180000Z_jr_1.json"
    path = write_run_record({"a": "한글"}, "b", key, local_dir=tmp_path)
    assert json.loads(open(path, encoding="utf-8").read()) == {"a": "한글"}


def test_failure_record_keeps_first_line_only():
    rec = failure_record({"table": "t", "result": None}, ValueError("no snapshots\nsecret detail"))
    assert rec["result"] == "failed"
    assert rec["error"] == "ValueError: no snapshots"


# ---------------------------------------------------------------------------
# ML-ready 앞뒤 범위 동등성 (T013, research R6)
# ---------------------------------------------------------------------------

KEYS = ["stack_code", "item_code", "measured_at"]


def _windowed(silver: pd.DataFrame, r: DayRange, lo, hi) -> pd.DataFrame:
    part = silver[(silver["ts_kst"] >= lo) & (silver["ts_kst"] <= hi)]
    return _sorted(in_range(to_ml_ready(part), "measured_at", r))


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(KEYS).reset_index(drop=True)


def test_ml_ready_context_equivalence():
    silver = build_silver()
    r = DayRange(date(2026, 11, 2), date(2026, 11, 3))
    full = _sorted(in_range(to_ml_ready(silver), "measured_at", r))
    lo, hi = ml_ready_window(r)
    windowed = _windowed(silver, r, lo, hi)

    assert list(windowed.columns) == COLUMNS
    assert len(full) > 0 and full["classification_eligible"].any()
    assert (full["label_entry_60m"] == 1).any()  # 진입 사례가 범위 안에 있다
    pd.testing.assert_frame_equal(windowed, full, check_dtype=False)


@pytest.mark.parametrize("side", ["lo", "hi"])
def test_ml_ready_window_one_slot_shorter_differs(side):
    """창을 30분 줄이면 결과가 달라진다: 테스트가 경계를 실제로 검사한다."""
    silver = build_silver()
    r = DayRange(date(2026, 11, 2), date(2026, 11, 3))
    full = _sorted(in_range(to_ml_ready(silver), "measured_at", r))
    lo, hi = ml_ready_window(r)
    step = pd.Timedelta(minutes=30)
    lo, hi = (lo + step, hi) if side == "lo" else (lo, hi - step)
    with pytest.raises(AssertionError):
        pd.testing.assert_frame_equal(_windowed(silver, r, lo, hi), full, check_dtype=False)


def test_ml_ready_schema_types_data_source_as_string(monkeypatch):
    """#48 머지 뒤 COLUMNS에 data_source가 붙어도 문자열로 잡힌다(double이면 "ktms"가 NaN이 됨)."""
    from smokestack_guard.silver import ml_ready

    import ktms_pipeline

    monkeypatch.setattr(ml_ready, "COLUMNS", [*COLUMNS, "data_source"])
    schema = ktms_pipeline.ml_ready_schema()
    assert schema.names[-1] == "data_source"
    assert schema["data_source"].dataType.typeName() == "string"
