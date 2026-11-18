"""ML-ready 잡 (T015, T033). spec 008 US1·US4, FR-005·006. `pytest -m iceberg`로 실행한다."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from ktms_cases import build_silver
from smokestack_guard.silver.ml_ready import COLUMNS, to_ml_ready

import glue_ktms_ml_ready
from ktms_pipeline import (
    DayRange,
    ensure_table,
    in_range,
    latest_snapshot_id,
    overwrite_range,
    qualified,
    silver_schema,
)

pytestmark = pytest.mark.iceberg

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=UTC)
TARGET = DayRange(date(2026, 11, 2), date(2026, 11, 3))
KEYS = ["stack_code", "item_code", "measured_at"]


def _silver_table(spark, name: str) -> str:
    table = f"tms_ml.{name}"
    ensure_table(spark, table, silver_schema(), "ts_kst", None)
    overwrite_range(
        spark,
        build_silver(),
        silver_schema(),
        table,
        "ts_kst",
        DayRange(date(2026, 11, 1), date(2026, 11, 4)),
        {},
    )
    return table


def _args(silver: str, ml: str, runs_dir, start="2026-11-02", end="2026-11-03") -> list[str]:
    return [
        "--silver_table",
        silver,
        "--ml_ready_table",
        ml,
        "--start_date",
        start,
        "--end_date",
        end,
        "--local",
        "--runs_dir",
        str(runs_dir),
        "--JOB_RUN_ID",
        "jr_ml",
    ]


def _record(runs_dir) -> dict:
    files = sorted((runs_dir / "silver2/_runs/ktms_ml_ready").glob("*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8"))


def test_ml_ready_matches_full_pandas(iceberg_spark, tmp_path):
    silver = _silver_table(iceberg_spark, "ktms_a")
    glue_ktms_ml_ready.main(_args(silver, "tms_ml.ktms_ml_ready_a", tmp_path), now=NOW)

    got = iceberg_spark.table(qualified("tms_ml.ktms_ml_ready_a")).toPandas()
    assert list(got.columns) == COLUMNS
    assert sorted(got["measured_at"].dt.date.astype(str).unique()) == ["2026-11-02", "2026-11-03"]

    expected = in_range(to_ml_ready(build_silver()), "measured_at", TARGET)
    got = got.sort_values(KEYS).reset_index(drop=True)
    expected = expected.sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(got, expected, check_dtype=False)

    saved = _record(tmp_path)
    assert saved["result"] == "succeeded"
    assert saved["rows"] == len(expected)
    assert saved["classification_eligible"] == int(expected["classification_eligible"].sum())
    assert saved["positives"] == int(
        (expected["classification_eligible"] & expected["label_entry_60m"].eq(1)).sum()
    )
    assert saved["positives"] > 0
    assert saved["snapshot_id"] == latest_snapshot_id(iceberg_spark, "tms_ml.ktms_ml_ready_a")


def test_no_silver_rows_fails_and_keeps_table(iceberg_spark, tmp_path):
    silver = _silver_table(iceberg_spark, "ktms_b")
    ml = "tms_ml.ktms_ml_ready_b"
    glue_ktms_ml_ready.main(_args(silver, ml, tmp_path), now=NOW)
    snap = latest_snapshot_id(iceberg_spark, ml)

    with pytest.raises(ValueError, match="no silver rows"):
        glue_ktms_ml_ready.main(
            _args(silver, ml, tmp_path, "2026-10-01", "2026-10-01"), now=NOW.replace(minute=1)
        )
    assert latest_snapshot_id(iceberg_spark, ml) == snap
    assert _record(tmp_path)["result"] == "failed"
