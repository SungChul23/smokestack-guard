"""Silver 잡 (T014, T032, T035). spec 008 US1·US4·US5. `pytest -m iceberg`로 실행한다."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from ktms_cases import put_snapshot, stack_item

import glue_ktms_silver
from ktms_pipeline import latest_snapshot_id, qualified

pytestmark = pytest.mark.iceberg

BUCKET = "smokestack-tms-raw-952900391026"
RUN_AT = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)  # KST 11-13 03:00
A = ("서울특별시", "가나다발전", "001")
B = ("부산광역시", "라마바소각", "002")
C = ("대구광역시", "사아자제철", "003")


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def _bronze(s3):
    put_snapshot(
        s3, BUCKET, _utc(2026, 11, 10, 14, 50), [stack_item(*A, "2026-11-10 23:30", nox="9")]
    )  # 범위 앞
    put_snapshot(
        s3,
        BUCKET,
        _utc(2026, 11, 10, 15, 10),
        [stack_item(*A, "2026-11-11 00:00", nox="10", sox="20")],
    )
    put_snapshot(  # 표지 없음
        s3,
        BUCKET,
        _utc(2026, 11, 11, 5, 0),
        [stack_item(*C, "2026-11-11 13:30", nox="99")],
        success=False,
    )
    put_snapshot(
        s3,
        BUCKET,
        _utc(2026, 11, 11, 12, 0),
        [stack_item(*A, "2026-11-11 20:30", nox="측정자료확인중")],
    )
    put_snapshot(  # 정정
        s3,
        BUCKET,
        _utc(2026, 11, 11, 13, 0),
        [stack_item(*A, "2026-11-11 20:30", nox="측정자료확인중(가동중지)")],
    )
    put_snapshot(
        s3, BUCKET, _utc(2026, 11, 12, 14, 40), [stack_item(*B, "2026-11-12 23:30", nox="1,910.17")]
    )
    put_snapshot(
        s3, BUCKET, _utc(2026, 11, 12, 15, 20), [stack_item(*B, "2026-11-13 00:00", nox="5")]
    )  # 오늘


def _args(table: str, runs_dir, *extra: str) -> list[str]:
    return [
        "--silver_table",
        table,
        "--local",
        "--runs_dir",
        str(runs_dir),
        "--JOB_RUN_ID",
        "jr_test",
        *extra,
    ]


def _record(runs_dir, prefix="silver2/_runs/ktms") -> dict:
    files = sorted((runs_dir / prefix).glob("*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8"))


def test_daily_run_writes_target_days_only(iceberg_spark, fake_s3, tmp_path):
    _bronze(fake_s3)
    table = "tms_job.ktms_daily"
    record = glue_ktms_silver.main(_args(table, tmp_path), s3=fake_s3, now=RUN_AT)

    df = iceberg_spark.table(qualified(table)).toPandas()
    assert sorted(df["ts_kst"].dt.date.astype(str).unique()) == ["2026-11-11", "2026-11-12"]
    assert "003" not in set(df["stack_code"])  # _SUCCESS 없는 폴더
    fixed = df[(df["stack_code"] == "001") & (df["ts_kst"] == datetime(2026, 11, 11, 20, 30))]
    assert fixed["status"].tolist() == ["stopped"]  # US1-2
    comma = df[df["stack_code"] == "002"]
    assert comma["value"].tolist() == [1910.17] and comma["status"].tolist() == ["ok"]
    assert len(df) == 4

    saved = _record(tmp_path)
    assert saved == json.loads(json.dumps(record, default=str))
    assert saved["result"] == "succeeded"
    assert saved["range"] == {"start": "2026-11-11", "end": "2026-11-12"}
    assert saved["source"]["ingest_dates"] == ["2026-11-10", "2026-11-12"]
    assert saved["rows"] == 4 and saved["empty_days"] == []
    assert saved["status_rows"] == {"ok": 3, "stopped": 1}
    assert saved["snapshot_id"] == latest_snapshot_id(iceberg_spark, table)


def test_no_snapshots_fails_and_keeps_table(iceberg_spark, fake_s3, tmp_path):
    _bronze(fake_s3)
    table = "tms_job.ktms_fail"
    glue_ktms_silver.main(_args(table, tmp_path), s3=fake_s3, now=RUN_AT)
    snap = latest_snapshot_id(iceberg_spark, table)

    with pytest.raises(ValueError, match="no snapshots"):
        glue_ktms_silver.main(
            _args(table, tmp_path, "--start_date", "2026-10-01", "--end_date", "2026-10-01"),
            s3=fake_s3,
            now=RUN_AT.replace(minute=1),
        )
    assert latest_snapshot_id(iceberg_spark, table) == snap
    saved = _record(tmp_path)
    assert saved["result"] == "failed" and saved["error"].startswith("ValueError: no snapshots")


def test_bad_arguments_leave_failure_record(fake_s3, tmp_path):
    with pytest.raises(ValueError, match="늦다"):
        glue_ktms_silver.main(
            _args(
                "tms_job.ktms_args",
                tmp_path,
                "--start_date",
                "2026-11-05",
                "--end_date",
                "2026-11-04",
            ),
            s3=fake_s3,
            now=RUN_AT,
        )
    assert _record(tmp_path)["result"] == "failed"


def test_synthetic_prefix_needs_c_change(iceberg_spark, fake_s3, tmp_path):
    _bronze(fake_s3)
    glue_ktms_silver.main(_args("tms_job.ktms_real", tmp_path), s3=fake_s3, now=RUN_AT)
    snap = latest_snapshot_id(iceberg_spark, "tms_job.ktms_real")

    with pytest.raises(ValueError, match="C의 read_bronze에 경로 인자 필요"):
        glue_ktms_silver.main(
            _args("tms_job.ktms_synthetic", tmp_path, "--source_prefix", "tms_synthetic/"),
            s3=fake_s3,
            now=RUN_AT.replace(minute=2),
        )
    assert latest_snapshot_id(iceberg_spark, "tms_job.ktms_real") == snap
    assert (
        latest_snapshot_id(iceberg_spark, "tms_job.ktms_synthetic") is None
    )  # 검사가 DDL보다 먼저
