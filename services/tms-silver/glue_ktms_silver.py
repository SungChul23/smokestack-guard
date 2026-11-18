"""K-TMS 원본 스냅샷을 Silver Iceberg 테이블로 갱신한다 (Glue Job 스크립트, 로컬 겸용). spec 008.

- 규칙은 C의 `smokestack_guard.silver.ktms`(read_bronze, to_silver, quality)를 수정 없이 쓴다.
- 처리 범위는 KST 측정일 `[start, end]`(기본: 끝난 최근 2일).
  원본은 UTC 수집일 `[start − 1, end + 1]`을 읽는다.
- 결과는 `tms_silver2.ktms`의 대상 범위만 Iceberg 커밋 1번으로 교체한다.
  원본·결과가 0행이면 쓰기 전에 실패한다.
- 실행 기록 `silver2/_runs/ktms/<시작 UTC>_<job_run_id>.json`을 성공·실패 모두 남긴다.
- 로그에는 범위·건수·버전만 남기고 데이터 값은 남기지 않는다.

계약: specs/a-platform/008-ktms-silver-pipeline/contracts/run-interface.md
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from smokestack_guard.silver import ktms

import ktms_pipeline as kp

TS_COL = "ts_kst"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--start_date", default=kp.AUTO)
    p.add_argument("--end_date", default=kp.AUTO)
    p.add_argument("--bucket", default=kp.DEFAULT_BUCKET)
    p.add_argument("--source_prefix", default=kp.DEFAULT_SOURCE_PREFIX)
    p.add_argument("--silver_table", default="tms_silver2.ktms")
    p.add_argument("--runs_prefix", default="silver2/_runs/ktms")
    p.add_argument("--max_days", type=int, default=7)
    p.add_argument("--package_md5", default="unknown")
    p.add_argument("--sfn_execution", default="manual")
    p.add_argument("--JOB_RUN_ID", dest="job_run_id", default="local")
    p.add_argument("--local", action="store_true", help="로컬 Spark(카탈로그는 호출자가 설정)")
    p.add_argument("--runs_dir", type=Path, help="--local일 때 실행 기록을 쓸 폴더")
    args, _unknown = p.parse_known_args(argv)  # Glue가 넘기는 --JOB_NAME 등은 무시한다
    if args.local and args.runs_dir is None:
        p.error("--local이면 --runs_dir가 필요하다")
    return args


def read_bronze(args, start, end, s3):
    if args.source_prefix == kp.DEFAULT_SOURCE_PREFIX:
        return ktms.read_bronze(args.bucket, start, end, s3=s3)
    return ktms.read_bronze(args.bucket, start, end, s3=s3, prefix=args.source_prefix)


def main(argv: list[str] | None = None, s3=None, now: datetime | None = None) -> dict:
    clock = time.monotonic()
    started_at = now or datetime.now(UTC)
    args = parse_args(argv)
    record: dict = {
        "table": args.silver_table,
        "result": None,
        "error": None,
        "job_run_id": args.job_run_id,
        "sfn_execution": args.sfn_execution,
        "range": None,
        "source": {"prefix": args.source_prefix, "ingest_dates": None, "snapshots": None},
        "rows": None,
        "rows_per_day": None,
        "empty_days": None,
        "status_rows": None,
        "duplicate_keys": None,
        "snapshot_id": None,
        "package_md5": args.package_md5,
        "versions": kp.runtime_versions(),
        "started_at": kp.iso(started_at),
        "finished_at": None,
    }
    key = kp.run_record_key(args.runs_prefix, started_at, args.job_run_id)
    local_dir = args.runs_dir if args.local else None

    try:
        r = kp.resolve_range(args.start_date, args.end_date, now=started_at, max_days=args.max_days)
        record["range"] = r.to_dict()
        kp.check_source_prefix(args.source_prefix)  # 읽기·DDL보다 먼저 (research R9)

        first, last = kp.ingest_dates(r, now=started_at)
        record["source"]["ingest_dates"] = [first.isoformat(), last.isoformat()]
        bronze = read_bronze(args, first, last, s3)
        if bronze.empty:
            raise ValueError(
                f"no snapshots in {args.source_prefix} for ingest_date {first}..{last}"
            )
        snapshots = int(bronze["snapshot"].nunique())
        record["source"]["snapshots"] = snapshots

        silver = kp.in_range(ktms.to_silver(bronze), TS_COL, r)
        dupes = int(bronze.duplicated(ktms.STACK + ["mesure_dt", "snapshot"]).sum())
        q = ktms.quality(silver, snapshots, dupes) if len(silver) else {}
        record |= {
            "rows": int(len(silver)),
            "rows_per_day": q.get("rows_per_day", {}),
            "status_rows": {k: int(v) for k, v in q.get("status", {}).items()},
            "duplicate_keys": q.get("duplicate_keys"),
        }
        record["empty_days"] = [
            d.isoformat() for d in r.dates() if d.isoformat() not in record["rows_per_day"]
        ]

        spark = kp.build_spark("tms-silver2-ktms")
        record["versions"] = kp.runtime_versions(spark)
        schema = kp.silver_schema()
        location = None if args.local else kp.table_location(args.bucket, args.silver_table)
        record["added_columns"] = kp.ensure_table(
            spark, args.silver_table, schema, TS_COL, location
        )
        record["snapshot_id"] = kp.overwrite_range(
            spark,
            silver,
            schema,
            args.silver_table,
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
    summary = {k: record[k] for k in ("table", "range", "rows", "empty_days", "snapshot_id")}
    summary |= {
        "snapshots": record["source"]["snapshots"],
        "elapsed_s": round(time.monotonic() - clock, 1),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return record


if __name__ == "__main__":
    main()
