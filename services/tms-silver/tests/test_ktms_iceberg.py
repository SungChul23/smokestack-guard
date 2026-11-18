"""Iceberg 범위 교체·버전 동작 (T012). spec 008 FR-009·010, SC-004·005.

`pytest -m iceberg`로 실행한다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from ktms_cases import build_silver

from ktms_pipeline import (
    DayRange,
    ensure_table,
    latest_snapshot_id,
    overwrite_range,
    qualified,
    silver_schema,
)

pytestmark = pytest.mark.iceberg

ALL = DayRange(date(2026, 11, 1), date(2026, 11, 4))
MID = DayRange(date(2026, 11, 2), date(2026, 11, 3))
KEYS = ["area_nm", "fact_manage_nm", "stack_code", "item", "ts_kst"]


def _table(spark, name: str) -> str:
    table = f"tms_test.{name}"
    ensure_table(spark, table, silver_schema(), "ts_kst", None)
    return table


def _read(spark, table: str, snapshot: int | None = None) -> pd.DataFrame:
    reader = spark.read if snapshot is None else spark.read.option("snapshot-id", snapshot)
    df = reader.table(qualified(table)).toPandas()
    return df.sort_values(KEYS).reset_index(drop=True)


def _day(df: pd.DataFrame, d: str) -> pd.DataFrame:
    return df[df["ts_kst"].dt.date.astype(str) == d].reset_index(drop=True)


def test_overwrite_range_keeps_other_days(iceberg_spark):
    table = _table(iceberg_spark, "keep_other_days")
    silver = build_silver()
    overwrite_range(
        iceberg_spark, silver, silver_schema(), table, "ts_kst", ALL, {"job_run_id": "a"}
    )
    before = _read(iceberg_spark, table)

    changed = silver.assign(value=silver["value"] + 1)
    overwrite_range(
        iceberg_spark, changed, silver_schema(), table, "ts_kst", MID, {"job_run_id": "b"}
    )
    after = _read(iceberg_spark, table)

    for d in ("2026-11-01", "2026-11-04"):
        pd.testing.assert_frame_equal(_day(after, d), _day(before, d))
    for d in ("2026-11-02", "2026-11-03"):
        diff = (_day(after, d)["value"] - _day(before, d)["value"]).dropna()
        assert len(diff) > 0 and (diff.round(6) == 1).all()
    assert len(after) == len(before)


def test_overwrite_is_idempotent(iceberg_spark):
    table = _table(iceberg_spark, "idempotent")
    silver = build_silver()
    overwrite_range(iceberg_spark, silver, silver_schema(), table, "ts_kst", ALL, {})
    first = _read(iceberg_spark, table)
    overwrite_range(iceberg_spark, silver, silver_schema(), table, "ts_kst", ALL, {})
    pd.testing.assert_frame_equal(_read(iceberg_spark, table), first)


def test_snapshot_read_is_stable(iceberg_spark):
    table = _table(iceberg_spark, "time_travel")
    silver = build_silver()
    snap = overwrite_range(
        iceberg_spark, silver, silver_schema(), table, "ts_kst", ALL, {"job_run_id": "x"}
    )
    kept = _read(iceberg_spark, table, snap)
    overwrite_range(
        iceberg_spark, silver.assign(value=0.0), silver_schema(), table, "ts_kst", MID, {}
    )
    assert latest_snapshot_id(iceberg_spark, table) != snap
    pd.testing.assert_frame_equal(_read(iceberg_spark, table, snap), kept)

    summary = iceberg_spark.sql(
        f"SELECT summary FROM {qualified(table)}.snapshots WHERE snapshot_id = {snap}"
    ).collect()[0]["summary"]
    assert summary["job_run_id"] == "x"


def test_empty_result_does_not_commit(iceberg_spark):
    table = _table(iceberg_spark, "empty")
    silver = build_silver()
    overwrite_range(iceberg_spark, silver, silver_schema(), table, "ts_kst", ALL, {})
    snap = latest_snapshot_id(iceberg_spark, table)
    outside = DayRange(date(2026, 11, 10), date(2026, 11, 11))
    with pytest.raises(ValueError, match="empty result"):
        overwrite_range(iceberg_spark, silver, silver_schema(), table, "ts_kst", outside, {})
    assert latest_snapshot_id(iceberg_spark, table) == snap


def test_range_deletes_rows_missing_from_new_result(iceberg_spark):
    table = _table(iceberg_spark, "delete_missing")
    silver = build_silver()
    overwrite_range(iceberg_spark, silver, silver_schema(), table, "ts_kst", ALL, {})
    gone = (silver["stack_code"] == "002") & (silver["ts_kst"].dt.date.astype(str) == "2026-11-02")
    day = DayRange(date(2026, 11, 2), date(2026, 11, 2))
    overwrite_range(iceberg_spark, silver[~gone], silver_schema(), table, "ts_kst", day, {})
    after = _read(iceberg_spark, table)
    assert not (
        (after["stack_code"] == "002") & (after["ts_kst"].dt.date.astype(str) == "2026-11-02")
    ).any()
    assert len(after) == len(silver) - int(gone.sum())


def test_ddl_partition_and_columns(iceberg_spark):
    table = _table(iceberg_spark, "ddl")
    overwrite_range(iceberg_spark, build_silver(), silver_schema(), table, "ts_kst", ALL, {})
    df = iceberg_spark.table(qualified(table))
    assert df.schema.names == silver_schema().names
    assert [f.dataType.simpleString() for f in df.schema.fields] == [
        f.dataType.simpleString() for f in silver_schema().fields
    ]
    parts = iceberg_spark.sql(f"SELECT partition FROM {qualified(table)}.partitions").collect()
    assert len(parts) == 4  # 11-01 ~ 11-04, 날짜 하나당 파티션 하나
    props = dict(iceberg_spark.sql(f"SHOW TBLPROPERTIES {qualified(table)}").collect())
    assert props.get("format-version") == "2"


def test_ensure_table_adds_new_trailing_column(iceberg_spark):
    """C가 ml_ready.COLUMNS 끝에 컬럼을 더해도(#48 data_source) 기존 테이블이 따라간다."""
    from pyspark.sql import types as T

    table = _table(iceberg_spark, "add_column")
    old = build_silver()
    overwrite_range(iceberg_spark, old, silver_schema(), table, "ts_kst", MID, {})
    before = latest_snapshot_id(iceberg_spark, table)

    wider = T.StructType([*silver_schema().fields, T.StructField("data_source", T.StringType())])
    assert ensure_table(iceberg_spark, table, wider, "ts_kst", None) == ["data_source"]
    assert ensure_table(iceberg_spark, table, wider, "ts_kst", None) == []  # 두 번째는 할 일 없음
    assert iceberg_spark.table(qualified(table)).columns == wider.names

    # 기존 행은 null로 읽히고, 컬럼 추가 전 버전도 같은 행으로 읽힌다(새 컬럼은 null)
    assert _read(iceberg_spark, table)["data_source"].isna().all()
    old_version = _read(iceberg_spark, table, before)
    assert len(old_version) == len(
        old[old["ts_kst"].dt.date.astype(str).isin(["2026-11-02", "2026-11-03"])]
    )
    assert old_version.get("data_source", pd.Series(dtype=object)).isna().all()

    day = DayRange(date(2026, 11, 2), date(2026, 11, 2))
    overwrite_range(iceberg_spark, old.assign(data_source="ktms"), wider, table, "ts_kst", day, {})
    after = _read(iceberg_spark, table)
    on_day = after["ts_kst"].dt.date.astype(str) == "2026-11-02"
    assert (after.loc[on_day, "data_source"] == "ktms").all()
    assert after.loc[~on_day, "data_source"].isna().all()  # 다시 계산하기 전 날짜는 null
