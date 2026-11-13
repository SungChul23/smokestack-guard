"""TW CEMS Silver → ML-ready (Glue Job 스크립트, 로컬 겸용).

--mode build
- silver/tw_cems/ 전체(36개월)를 경로로 읽어 ml_ready_spark.to_ml_ready로 만든다.
- measured_at 범위로 --files개 파일로 나누고 파일 안을 정렬해
  silver/tw_cems_ml_ready/에 전체 덮어쓴다.
- 시작할 때 latest.json을 지우고, 성공한 뒤에만 runs/<ts>.json과 latest.json을 쓴다.
  latest.json이 없으면 마지막 build는 실패했거나 진행 중이다.

--mode compare
- 출력과 정답지(C의 pandas 결과)를 35컬럼 비교해 compare/<ts>.json을 쓴다.
  불일치가 있어도 Job은 성공한다.

로그에는 경로·건수·버전만 남기고 값은 남기지 않는다.
계약: specs/a-platform/005-tw-cems-ml-ready-spark/contracts/run-interface.md §1
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from smokestack_guard.silver.ml_ready import COLUMNS

import ml_ready_spark as mrs

MAX_FILES = 32


# ---------------------------------------------------------------------------
# 인자와 경로
# ---------------------------------------------------------------------------


def _files(value: str) -> int:
    n = int(value)
    if not 1 <= n <= MAX_FILES:
        raise argparse.ArgumentTypeError(f"--files는 1~{MAX_FILES}이어야 한다: {value}")
    return n


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["build", "compare"], default="build")
    parser.add_argument("--bucket", default="smokestack-tms-raw-952900391026")
    parser.add_argument("--source_prefix", default="silver/tw_cems")
    parser.add_argument("--table_prefix", default="silver/tw_cems_ml_ready")
    parser.add_argument("--runs_prefix", default="silver/_runs/tw_cems_ml_ready")
    parser.add_argument("--files", type=_files, default=6)
    parser.add_argument(
        "--reference", default="s3://smokestack-cems-local-eda-952900391026/ml_ready/part.parquet"
    )
    parser.add_argument("--package_md5", default="unknown")
    parser.add_argument("--JOB_RUN_ID", dest="job_run_id", default="local")
    parser.add_argument("--local", action="store_true", help="로컬 Spark로 실행")
    parser.add_argument("--source_path")
    parser.add_argument("--output_path")
    parser.add_argument("--runs_path")
    parser.add_argument("--reference_path")

    # Glue가 넘기는 --JOB_NAME, --TempDir 등은 무시한다.
    args, _unknown = parser.parse_known_args(argv)
    if args.local and not (args.source_path and args.output_path and args.runs_path):
        parser.error("--local이면 --source_path, --output_path, --runs_path가 필요하다")
    if args.local and args.mode == "compare" and not args.reference_path:
        parser.error("--local compare에는 --reference_path가 필요하다")
    return args


def resolve(args: argparse.Namespace) -> dict[str, str]:
    if args.local:
        return {
            "source": str(args.source_path),
            "output": str(args.output_path),
            "reference": str(args.reference_path or ""),
        }
    return {
        "source": f"s3://{args.bucket}/{args.source_prefix.strip('/')}/",
        "output": f"s3://{args.bucket}/{args.table_prefix.strip('/')}/",
        "reference": args.reference,
    }


class RunStore:
    """실행 기록 저장소. 로컬은 폴더, Glue는 S3 runs_prefix."""

    def __init__(self, args: argparse.Namespace):
        self.local = args.local
        self.root = Path(args.runs_path) if args.local else None
        self.bucket = args.bucket
        self.prefix = args.runs_prefix.strip("/")
        self._s3 = None

    def _client(self):
        if self._s3 is None:
            import boto3

            self._s3 = boto3.client("s3")
        return self._s3

    def delete(self, name: str) -> None:
        if self.local:
            (self.root / name).unlink(missing_ok=True)
        else:
            self._client().delete_object(Bucket=self.bucket, Key=f"{self.prefix}/{name}")

    def write(self, name: str, record: dict) -> None:
        body = json.dumps(record, ensure_ascii=False, indent=2, default=str)
        if self.local:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        else:
            self._client().put_object(
                Bucket=self.bucket,
                Key=f"{self.prefix}/{name}",
                Body=body.encode("utf-8"),
                ContentType="application/json",
            )


def build_spark(local: bool) -> SparkSession:
    builder = SparkSession.builder.appName("tms-silver-tw-cems-ml-ready")
    if local:
        builder = builder.master("local[2]")
    spark = builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")  # timestamps are wall clocks
    spark.conf.set("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
    return spark


def runtime_versions(spark: SparkSession) -> dict[str, str]:
    versions = {"spark": spark.version, "python": platform.python_version()}
    for name in ("pandas", "numpy"):
        try:
            versions[name] = __import__(name).__version__
        except ImportError:
            versions[name] = "missing"
    return versions


# ---------------------------------------------------------------------------
# build / compare
# ---------------------------------------------------------------------------


def silver_months(silver: DataFrame) -> list[str]:
    if {"year", "month"} <= set(silver.columns):
        rows = silver.select("year", "month").distinct().collect()
        return sorted(f"{int(r.year):04d}-{int(r.month):02d}" for r in rows)
    rows = silver.select(F.date_format("ts_local", "yyyy-MM").alias("m")).distinct().collect()
    return sorted(r.m for r in rows)


def write_ml_ready(df: DataFrame, output: str, files: int) -> None:
    (
        df.repartitionByRange(files, "measured_at")
        .sortWithinPartitions("measured_at", "stack_code", "item_code")
        .write.mode("overwrite")
        .parquet(output)
    )


def run_build(spark, args, paths, store, base: dict) -> dict:
    store.delete("latest.json")  # 이후 실패하면 latest.json이 없다

    silver = spark.read.parquet(paths["source"])
    silver_rows = silver.count()
    if silver_rows == 0:
        raise ValueError("empty silver input")
    months = silver_months(silver)

    norm = mrs.normalize(silver).persist(StorageLevel.MEMORY_AND_DISK)
    selected_rows = norm.count()
    if selected_rows == 0:
        raise ValueError("no ml-ready target rows")
    deduped, duplicate_keys = mrs.dedupe(norm)
    out = mrs.add_features(deduped, "tw_cems")
    if out.columns != COLUMNS:
        raise ValueError("column contract mismatch")
    out = out.persist(StorageLevel.MEMORY_AND_DISK)
    try:
        stats = mrs.ml_ready_stats(out)
        write_ml_ready(out, paths["output"], args.files)
    finally:
        out.unpersist()
        norm.unpersist()

    record = base | {
        "source": paths["source"],
        "output": paths["output"],
        "silver_months": months,
        "silver_rows": silver_rows,
        "selected_rows": selected_rows,
        "duplicate_keys": duplicate_keys,
        **stats,
        "files": args.files,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    store.write(f"runs/{base['run_ts']}.json", record)
    store.write("latest.json", record)  # 성공한 뒤에만
    return record


def run_compare(spark, args, paths, store, base: dict) -> dict:
    ours = spark.read.parquet(paths["output"])
    theirs, original_type = mrs.read_reference(spark, paths["reference"])
    result = mrs.compare(ours, theirs)
    record = base | {
        "output": paths["output"],
        "reference": paths["reference"],
        "theirs_measured_at_type": original_type,
        **result,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    store.write(f"compare/{base['run_ts']}.json", record)
    return record


def main(argv: list[str] | None = None) -> dict:
    started = time.monotonic()
    now = datetime.now(UTC)
    args = parse_args(argv)
    paths = resolve(args)
    spark = build_spark(args.local)
    store = RunStore(args)
    base = {
        "run_ts": now.strftime("%Y%m%dT%H%M%SZ"),
        "job_run_id": args.job_run_id,
        "mode": args.mode,
        "package_md5": args.package_md5,
        "versions": runtime_versions(spark),
        "started_at": now.isoformat(timespec="seconds"),
    }

    run = run_build if args.mode == "build" else run_compare
    record = run(spark, args, paths, store, base)

    summary_keys = (
        ["mode", "source", "output", "silver_rows", "selected_rows", "duplicate_keys",
         "output_rows", "eligible_positive_rows", "files"]
        if args.mode == "build"
        else ["mode", "output", "reference", "ours_rows", "theirs_rows", "only_ours",
              "only_theirs", "passed"]
    )  # fmt: skip
    summary = {k: record.get(k) for k in summary_keys}
    summary["elapsed_s"] = round(time.monotonic() - started, 1)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return record


if __name__ == "__main__":
    main()
