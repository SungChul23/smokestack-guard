"""TW CEMS 원본 JSONL 한 달치를 Athena EDA용 Parquet으로 바꾼다 (Glue Job 스크립트, 로컬 겸용).

포맷 변환만 한다:
- 고정 스키마를 쓰지 않는다. 그 달에 나온 모든 키를 컬럼으로 보존한다.
- 모든 원본 값을 원문 문자열로 둔다. 행을 거르거나 값을 바꾸지 않는다.
- 손상된 줄도 `_corrupt_record`에 원문으로 남겨 행 수를 맞춘다.
- 각 행에 원본 파일 경로(`source_file`)를 붙인다.
- 출력은 `<prefix>/year=YYYY/month=MM/`에 월 단위로 덮어쓴다.

계약: specs/a-platform/003-tw-cems-eda/contracts/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

CORRUPT_COLUMN = "_corrupt_record"
SOURCE_FILE_COLUMN = "source_file"
OUTPUT_FILES_PER_MONTH = 2

_YEAR_RE = re.compile(r"^\d{4}$")
_MONTH_RE = re.compile(r"^(0[1-9]|1[0-2])$")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Job 인자를 읽는다. Glue가 덧붙이는 인자(--JOB_NAME, --TempDir 등)는 무시한다."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", required=True, help="YYYY")
    parser.add_argument("--month", required=True, help="MM (두 자리)")
    parser.add_argument("--raw_bucket", default="smokestack-tms-raw-952900391026")
    parser.add_argument("--raw_prefix", default="bronze/tw_cems/historical")
    parser.add_argument("--eda_bucket", default="smokestack-tms-eda-952900391026")
    parser.add_argument("--output_prefix", default="tw_cems_raw")
    parser.add_argument("--local", action="store_true", help="로컬 Spark로 실행")
    parser.add_argument("--input_path", help="로컬 입력 파일 (--local)")
    parser.add_argument("--output_path", help="로컬 출력 폴더 (--local)")

    args, _unknown = parser.parse_known_args(argv)

    if not _YEAR_RE.match(args.year):
        parser.error(f"--year는 4자리여야 한다: {args.year!r}")
    if not _MONTH_RE.match(args.month):
        parser.error(f"--month는 01~12 두 자리여야 한다: {args.month!r}")
    if args.local and not (args.input_path and args.output_path):
        parser.error("--local에는 --input_path와 --output_path가 필요하다")
    return args


def resolve_paths(args: argparse.Namespace) -> tuple[str, str]:
    """(입력 파일, 출력 월 폴더) 경로를 만든다."""
    partition = f"year={args.year}/month={args.month}/"
    if args.local:
        return args.input_path, f"{args.output_path.rstrip('/')}/{partition}"
    input_path = (
        f"s3://{args.raw_bucket}/{args.raw_prefix.strip('/')}/{args.year}-{args.month}.jsonl"
    )
    output_path = f"s3://{args.eda_bucket}/{args.output_prefix.strip('/')}/{partition}"
    return input_path, output_path


def build_spark(local: bool) -> SparkSession:
    builder = SparkSession.builder.appName("tms-eda-tw-cems-parquet")
    if local:
        builder = (
            builder.master("local[2]")
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.ui.enabled", "false")
        )
    return builder.getOrCreate()


def check_column_conflicts(columns: list[str]) -> None:
    """소문자로 바꿨을 때 겹치는 컬럼이 있으면 실패시킨다.

    Glue 카탈로그와 Athena는 컬럼 이름의 대소문자를 구분하지 않아 테이블에서 충돌한다.
    """
    seen: dict[str, list[str]] = {}
    for name in columns:
        seen.setdefault(name.lower(), []).append(name)
    conflicts = sorted(names for names in seen.values() if len(names) > 1)
    if conflicts:
        raise ValueError(f"대소문자만 다른 키가 있다: {conflicts}")


def convert(spark: SparkSession, input_path: str, output_path: str) -> dict:
    """월 파일 하나를 변환한다. 추가 count()로 원본을 다시 읽지 않는다."""
    # 대소문자를 구분하지 않으면 Spark가 스키마 추론 단계에서 COLUMN_ALREADY_EXISTS로 실패해
    # 어떤 키끼리 충돌했는지 알 수 없다. 읽는 동안만 구분하게 해서 아래 검사가 이름을 짚게 한다.
    previous_case_sensitive = spark.conf.get("spark.sql.caseSensitive", "false")
    spark.conf.set("spark.sql.caseSensitive", "true")
    try:
        df = (
            spark.read.option("primitivesAsString", "true")
            .option("mode", "PERMISSIVE")
            .option("columnNameOfCorruptRecord", CORRUPT_COLUMN)
            .json(input_path)
        )
        columns = list(df.columns)
    finally:
        spark.conf.set("spark.sql.caseSensitive", previous_case_sensitive)
    check_column_conflicts(columns)

    (
        df.withColumn(SOURCE_FILE_COLUMN, F.col("_metadata.file_path"))
        # coalesce는 읽기·파싱까지 병렬도를 줄이므로 repartition으로 쓰기 직전에만 모은다.
        .repartition(OUTPUT_FILES_PER_MONTH)
        .write.mode("overwrite")
        .option("compression", "snappy")
        # Glue는 기본으로 _SUCCESS를 쓰지 않는다. run_backfill --only-missing이 이 표지로
        # 완료 여부를 판단하므로 명시적으로 켠다(로컬 Spark는 원래 켜져 있다).
        .option("mapreduce.fileoutputcommitter.marksuccessfuljobs", "true")
        .parquet(output_path)
    )

    return {
        "input_path": input_path,
        "output_path": output_path,
        "column_count": len(columns) + 1,
        "columns": columns + [SOURCE_FILE_COLUMN],
        "spark_version": spark.version,
    }


def main(argv: list[str] | None = None) -> dict:
    started = time.monotonic()
    args = parse_args(argv)
    input_path, output_path = resolve_paths(args)
    spark = build_spark(args.local)

    summary = convert(spark, input_path, output_path)
    summary["elapsed_s"] = round(time.monotonic() - started, 1)
    # 요약만 남긴다. 데이터 값은 로그에 쓰지 않는다.
    print(json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main(sys.argv[1:])
