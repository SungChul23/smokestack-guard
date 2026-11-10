"""TW CEMS 원본 JSONL 한 달치를 Silver로 바꾼다 (Glue Job 스크립트, 로컬 겸용).

- 규칙은 C의 `smokestack_guard.silver.tw_cems_spark`(read_raw, to_silver)를 수정 없이 쓴다.
- 쓰기 전에 검사한다: 입력 월과 다른 달의 행이 있거나 결과가 0행이면 실패한다.
- 출력은 `silver/tw_cems/year=YYYY/month=MM/`. 동적 파티션 덮어쓰기라 그 달만 교체된다.
  작은 파일이 쌓이지 않도록 한 달을 `--files_per_month`개(기본 1) 파일로 쓴다.
- 쓰기가 성공한 뒤에만 실행 기록 `silver/_runs/tw_cems/YYYY-MM.json`을 남긴다.
- 로그에는 경로·건수·버전만 남기고 데이터 값은 남기지 않는다.

계약: specs/a-platform/004-tw-cems-silver-glue/contracts/run-interface.md §1
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from smokestack_guard.silver import tw_cems_spark
from smokestack_guard.silver.tw_cems import RAW

STATUSES = ("ok", "not_monitored", "other_code", "partial", "invalid")

_YEAR_RE = re.compile(r"^\d{4}$")
_MONTH_RE = re.compile(r"^(0[1-9]|1[0-2])$")


# ---------------------------------------------------------------------------
# 인자와 경로
# ---------------------------------------------------------------------------


def _year(value: str) -> str:
    if not _YEAR_RE.match(value):
        raise argparse.ArgumentTypeError(f"YYYY 형식이어야 한다: {value!r}")
    return value


def _month(value: str) -> str:
    if not _MONTH_RE.match(value):
        raise argparse.ArgumentTypeError(f"MM(01~12) 형식이어야 한다: {value!r}")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=_year, required=True)
    parser.add_argument("--month", type=_month, required=True)
    parser.add_argument("--raw_bucket", default="smokestack-tms-raw-952900391026")
    parser.add_argument("--raw_prefix", default="bronze/tw_cems/historical")
    parser.add_argument("--silver_bucket", default="smokestack-tms-raw-952900391026")
    parser.add_argument("--table_prefix", default="silver/tw_cems")
    parser.add_argument("--runs_prefix", default="silver/_runs/tw_cems")
    parser.add_argument("--package_md5", default="unknown")
    parser.add_argument("--files_per_month", type=int, default=1, help="한 달 Parquet 파일 수")
    parser.add_argument("--JOB_RUN_ID", dest="job_run_id", default="local")
    parser.add_argument("--local", action="store_true", help="로컬 Spark로 실행")
    parser.add_argument("--input_path")
    parser.add_argument("--output_path")
    parser.add_argument("--runs_path")

    # Glue가 넘기는 --JOB_NAME, --TempDir 등은 무시한다.
    args, _unknown = parser.parse_known_args(argv)
    if args.files_per_month < 1:
        parser.error("--files_per_month는 1 이상이어야 한다")
    if args.local and not (args.input_path and args.output_path and args.runs_path):
        parser.error("--local이면 --input_path, --output_path, --runs_path가 필요하다")
    return args


@dataclass(frozen=True)
class Paths:
    source: str
    output: str  # 테이블 루트 (partitionBy로 year=/month= 아래에 쓴다)
    partition: str
    run_record_key: str  # Glue: S3 키, 로컬: 파일 경로


def resolve_paths(args: argparse.Namespace) -> Paths:
    month = f"{args.year}-{args.month}"
    if args.local:
        output = str(Path(args.output_path))
        return Paths(
            source=str(args.input_path),
            output=output,
            partition=str(Path(output) / f"year={args.year}" / f"month={args.month}"),
            run_record_key=str(Path(args.runs_path) / f"{month}.json"),
        )
    table = args.table_prefix.strip("/")
    output = f"s3://{args.silver_bucket}/{table}/"
    return Paths(
        source=f"s3://{args.raw_bucket}/{args.raw_prefix.strip('/')}/{month}.jsonl",
        output=output,
        partition=f"{output}year={args.year}/month={args.month}/",
        run_record_key=f"{args.runs_prefix.strip('/')}/{month}.json",
    )


def build_spark(local: bool) -> SparkSession:
    builder = SparkSession.builder.appName("tms-silver-tw-cems")
    if local:
        builder = builder.master("local[2]")
    spark = builder.getOrCreate()
    # 타임스탬프는 벽시계 값이다. 그 달 파티션만 교체한다.
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    return spark


# ---------------------------------------------------------------------------
# 변환과 검사
# ---------------------------------------------------------------------------


def read_input(spark: SparkSession, source: str) -> tuple[DataFrame, int]:
    """C의 read_raw로 읽고 Silver가 쓰는 원본 키만 남긴다. 다시 읽지 않도록 persist한다."""
    raw = tw_cems_spark.read_raw(spark, source)
    raw = raw.toDF(*[c.lower() for c in raw.columns])
    raw = raw.select(*[c for c in RAW if c in raw.columns])
    raw = raw.persist(StorageLevel.MEMORY_AND_DISK)
    return raw, raw.count()


def with_partitions(silver: DataFrame) -> DataFrame:
    # tw_cems_spark.build()와 같은 식이어야 한다(테스트로 확인).
    return silver.withColumn("year", F.date_format("ts_local", "yyyy")).withColumn(
        "month", F.date_format("ts_local", "MM")
    )


def collect_counts(silver: DataFrame) -> dict[tuple[str, str], dict[str, int]]:
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for row in silver.groupBy("year", "month", "status").count().collect():
        counts.setdefault((row["year"], row["month"]), {})[row["status"]] = row["count"]
    return counts


def check_months(counts: dict[tuple[str, str], dict[str, int]], year: str, month: str) -> None:
    """쓰기 전에 호출한다. 다른 달 행이 있으면 그 달 파티션을 덮어쓰게 되므로 멈춘다."""
    if not counts:
        raise ValueError(f"empty silver for {year}-{month}")
    others = {
        f"{y}-{m}": sum(by_status.values())
        for (y, m), by_status in sorted(counts.items())
        if (y, m) != (year, month)
    }
    if others:
        raise ValueError(f"month mismatch: expected {year}-{month}, found {json.dumps(others)}")


def write_silver(silver: DataFrame, output: str, files: int = 1) -> None:
    # 집계 뒤 조각 수(월 36개 안팎)대로 쓰면 파일당 1MB 안팎이 된다. 쓰기 직전에만 합친다.
    silver.coalesce(files).write.mode("overwrite").partitionBy("year", "month").parquet(output)


# ---------------------------------------------------------------------------
# 실행 기록
# ---------------------------------------------------------------------------


def runtime_versions(spark: SparkSession) -> dict[str, str]:
    versions = {"spark": spark.version, "python": platform.python_version()}
    for name in ("pandas", "numpy"):  # tw_cems.py import 확인용. 결과와는 무관하다(research R1)
        try:
            versions[name] = __import__(name).__version__
        except ImportError:
            versions[name] = "missing"
    return versions


def build_run_record(
    *,
    args: argparse.Namespace,
    paths: Paths,
    input_rows: int,
    status_rows: dict[str, int],
    versions: dict[str, str],
    started_at: datetime,
    finished_at: datetime,
) -> dict:
    status_rows = {s: int(status_rows.get(s, 0)) for s in STATUSES} | {
        s: int(n) for s, n in status_rows.items() if s not in STATUSES
    }
    record = {
        "month": f"{args.year}-{args.month}",
        "job_run_id": args.job_run_id,
        "source": paths.source,
        "output": paths.partition,
        "input_rows": int(input_rows),
        "silver_rows": sum(status_rows.values()),
        "status_rows": status_rows,
        "package_md5": args.package_md5,
        "versions": versions,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
    }
    assert record["silver_rows"] == sum(record["status_rows"].values())
    return record


def write_run_record(record: dict, args: argparse.Namespace, paths: Paths) -> None:
    body = json.dumps(record, ensure_ascii=False, indent=2)
    if args.local:
        path = Path(paths.run_record_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return
    import boto3

    boto3.client("s3").put_object(
        Bucket=args.silver_bucket,
        Key=paths.run_record_key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> dict:
    started = time.monotonic()
    started_at = datetime.now(UTC)
    args = parse_args(argv)
    paths = resolve_paths(args)
    spark = build_spark(args.local)

    raw, input_rows = read_input(spark, paths.source)
    silver = with_partitions(tw_cems_spark.to_silver(raw)).persist(StorageLevel.MEMORY_AND_DISK)
    try:
        counts = collect_counts(silver)
        check_months(counts, args.year, args.month)  # 쓰기보다 먼저
        write_silver(silver, paths.output, args.files_per_month)
    finally:
        silver.unpersist()
        raw.unpersist()

    record = build_run_record(
        args=args,
        paths=paths,
        input_rows=input_rows,
        status_rows=counts[(args.year, args.month)],
        versions=runtime_versions(spark),
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    write_run_record(record, args, paths)  # 데이터 쓰기가 성공한 뒤에만

    summary = {k: record[k] for k in ("month", "source", "output", "input_rows", "silver_rows")}
    summary |= {
        "status_rows": record["status_rows"],
        "package_md5": record["package_md5"],
        "versions": record["versions"],
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return record


if __name__ == "__main__":
    main()
