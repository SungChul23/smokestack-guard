"""K-TMS Silver Iceberg 테이블로 ML-ready 테이블을 갱신한다 (Glue Job, 로컬 겸용). spec 008.

- 규칙은 C의 `smokestack_guard.silver.ml_ready.to_ml_ready`를 수정 없이 쓴다
  (35컬럼 = `ml_ready.COLUMNS`).
- 처리 범위는 KST 날짜 `[start, end]`.
  입력은 Silver `[start 00:00 − 150분, end + 1일 00:30]`(양 끝 포함)이고,
  결과는 대상 범위 행만 `tms_silver2.ktms_ml_ready`에 커밋 1번으로 교체한다(research R6).
- 매일 실행 직후 `end`일 마지막 1시간의 라벨은 다음날 Silver가 없어 비어 있고,
  다음날 실행에서 채워진다.
- 실행 기록 `silver2/_runs/ktms_ml_ready/<시작 UTC>_<job_run_id>.json`을 성공·실패 모두 남긴다.

계약: specs/a-platform/008-ktms-silver-pipeline/contracts/run-interface.md
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from smokestack_guard.silver import ml_ready

import ktms_pipeline as kp

TS_COL = "measured_at"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--start_date", default=kp.AUTO)
    p.add_argument("--end_date", default=kp.AUTO)
    p.add_argument("--bucket", default=kp.DEFAULT_BUCKET)
    p.add_argument("--silver_table", default="tms_silver2.ktms")
    p.add_argument("--ml_ready_table", default="tms_silver2.ktms_ml_ready")
    p.add_argument("--runs_prefix", default="silver2/_runs/ktms_ml_ready")
    p.add_argument("--package_md5", default="unknown")
    p.add_argument("--sfn_execution", default="manual")
    p.add_argument("--JOB_RUN_ID", dest="job_run_id", default="local")
    p.add_argument("--local", action="store_true", help="로컬 Spark(카탈로그는 호출자가 설정)")
    p.add_argument("--runs_dir", type=Path, help="--local일 때 실행 기록을 쓸 폴더")
    args, _unknown = p.parse_known_args(argv)
    if args.local and args.runs_dir is None:
        p.error("--local이면 --runs_dir가 필요하다")
    return args


def main(argv: list[str] | None = None, s3=None, now: datetime | None = None) -> dict:
    clock = time.monotonic()
    started_at = now or datetime.now(UTC)
    args = parse_args(argv)
    record: dict = {
        "table": args.ml_ready_table,
        "result": None,
        "error": None,
        "job_run_id": args.job_run_id,
        "sfn_execution": args.sfn_execution,
        "range": None,
        "source": {"table": args.silver_table, "window": None},
        "input_rows": None,
        "rows": None,
        "rows_per_day": None,
        "classification_eligible": None,
        "regression_eligible": None,
        "positives": None,
        "snapshot_id": None,
        "package_md5": args.package_md5,
        "versions": kp.runtime_versions(),
        "started_at": kp.iso(started_at),
        "finished_at": None,
    }
    key = kp.run_record_key(args.runs_prefix, started_at, args.job_run_id)
    local_dir = args.runs_dir if args.local else None

    try:
        r = kp.resolve_range(args.start_date, args.end_date, now=started_at)
        record["range"] = r.to_dict()
        lo, hi = kp.ml_ready_window(r)
        record["source"]["window"] = [lo.isoformat(), hi.isoformat()]

        spark = kp.build_spark("tms-silver2-ktms-ml-ready")
        record["versions"] = kp.runtime_versions(spark)
        silver = kp.read_range(spark, args.silver_table, "ts_kst", lo, hi)
        record["input_rows"] = int(len(silver))
        if silver.empty:
            raise ValueError(f"no silver rows in {args.silver_table} for {lo}..{hi}")

        result = kp.in_range(ml_ready.to_ml_ready(silver), TS_COL, r)
        eligible = result["classification_eligible"].astype(bool)
        days = result[TS_COL].dt.date.astype(str).value_counts().sort_index()
        record |= {
            "rows": int(len(result)),
            "rows_per_day": {d: int(n) for d, n in days.items()},
            "classification_eligible": int(eligible.sum()),
            "regression_eligible": int(result["regression_eligible"].astype(bool).sum()),
            "positives": int((eligible & result["label_entry_60m"].eq(1)).sum()),
        }

        schema = kp.ml_ready_schema()
        location = None if args.local else kp.table_location(args.bucket, args.ml_ready_table)
        kp.ensure_table(spark, args.ml_ready_table, schema, TS_COL, location)
        record["snapshot_id"] = kp.overwrite_range(
            spark,
            result,
            schema,
            args.ml_ready_table,
            TS_COL,
            r,
            {"job_run_id": args.job_run_id, "range": f"{r.start}..{r.end}"},
        )
        record["result"] = "succeeded"
    except Exception as exc:
        record = kp.failure_record(record, exc)
        record["finished_at"] = kp.iso(datetime.now(UTC))
        kp.write_run_record(record, args.bucket, key, s3=s3, local_dir=local_dir)
        print(
            json.dumps(
                {"result": "failed", "error": record["error"], "run_record": key},
                ensure_ascii=False,
            )
        )
        raise

    record["finished_at"] = kp.iso(datetime.now(UTC))
    kp.write_run_record(record, args.bucket, key, s3=s3, local_dir=local_dir)
    summary = {
        k: record[k]
        for k in (
            "table",
            "range",
            "input_rows",
            "rows",
            "classification_eligible",
            "positives",
            "snapshot_id",
        )
    }
    summary["elapsed_s"] = round(time.monotonic() - clock, 1)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return record


if __name__ == "__main__":
    main()
