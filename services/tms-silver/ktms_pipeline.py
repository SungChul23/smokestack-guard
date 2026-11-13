"""K-TMS Silver·ML-ready 잡이 함께 쓰는 부분 (008).

- 처리 범위: KST 측정일 `[start, end]`. `auto`는 끝난 최근 2일이다.
- 원본 범위: UTC 수집일 `[start − 1, min(end + 1, 오늘 UTC)]`.
- ML-ready 입력: Silver `[start 00:00 − 150분, end + 1일 00:30]`(양 끝 포함).
- 쓰기: Iceberg 테이블의 대상 범위를 커밋 1번으로 교체한다. 0행이면 쓰기 전에 실패한다.
- 실행 기록: `<runs_prefix>/<시작 UTC>_<job_run_id>.json`. 실패한 시도도 남긴다.

규칙(값 계산)은 C의 `smokestack_guard.silver`를 수정 없이 쓴다.

spec: specs/a-platform/008-ktms-silver-pipeline/spec.md
설계: research.md R3~R10, data-model.md, contracts/run-interface.md
"""

from __future__ import annotations

import inspect
import json
import platform
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
from smokestack_guard.silver import ktms, ml_ready

AUTO = "auto"
DEFAULT_BUCKET = "smokestack-tms-raw-952900391026"
DEFAULT_SOURCE_PREFIX = ktms.PREFIX  # "tms_cleansys/"
CATALOG = "glue_catalog"
ML_LOOKBACK = timedelta(minutes=150)  # lag 150, rolling 6칸, 기준치 변경 창
ML_LOOKAHEAD = timedelta(minutes=30)  # 마지막 칸 23:30의 +60분 = 다음날 00:30

# ---------------------------------------------------------------------------
# 처리 범위
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DayRange:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def start_ts(self) -> datetime:
        return datetime.combine(self.start, datetime.min.time())

    @property
    def end_ts(self) -> datetime:
        """끝 다음날 00:00 (반열린 구간의 끝)."""
        return datetime.combine(self.end + timedelta(days=1), datetime.min.time())

    def dates(self) -> list[date]:
        return [self.start + timedelta(days=n) for n in range(self.days)]

    def to_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


def _parse_day(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name}는 YYYY-MM-DD 또는 auto여야 한다: {value!r}") from exc


def resolve_range(
    start: str, end: str, now: datetime | None = None, max_days: int | None = None
) -> DayRange:
    """data-model §5. `auto`는 끝난 최근 2일, 진행 중인 오늘(KST)은 받지 않는다."""
    last = ktms.last_complete_day(now)
    if (start == AUTO) != (end == AUTO):
        raise ValueError("start_date와 end_date는 둘 다 날짜이거나 둘 다 auto여야 한다")
    if start == AUTO:
        r = DayRange(last - timedelta(days=1), last)
    else:
        r = DayRange(_parse_day(start, "start_date"), _parse_day(end, "end_date"))
    if r.start > r.end:
        raise ValueError(f"start_date({r.start})가 end_date({r.end})보다 늦다")
    if r.end > last:
        raise ValueError(f"end_date({r.end})는 끝난 날짜(≤ {last}, KST)여야 한다")
    if max_days is not None and r.days > max_days:
        raise ValueError(f"한 번에 {max_days}일까지 처리한다: {r.days}일 요청")
    return r


def ingest_dates(r: DayRange, now: datetime | None = None) -> tuple[date, date]:
    """읽을 원본 UTC 수집일(research R6).

    KST D 00:00 = UTC D−1 15:00이고, 늦게 온 값은 다음날까지 본다.
    """
    today_utc = (now or datetime.now(UTC)).astimezone(UTC).date()
    return r.start - timedelta(days=1), min(r.end + timedelta(days=1), today_utc)


def ml_ready_window(r: DayRange) -> tuple[datetime, datetime]:
    """ML-ready 계산에 넣을 Silver 범위. 양 끝 포함."""
    return r.start_ts - ML_LOOKBACK, r.end_ts + ML_LOOKAHEAD


def check_source_prefix(prefix: str, read_bronze=ktms.read_bronze) -> None:
    """합성 등 다른 원본 경로는 C의 read_bronze가 경로 인자를 받을 때만 읽는다(research R9)."""
    if prefix == DEFAULT_SOURCE_PREFIX:
        return
    if "prefix" not in inspect.signature(read_bronze).parameters:
        raise ValueError(
            f"원본 경로 {prefix!r}를 읽으려면 C의 read_bronze에 경로 인자 필요 "
            f"(지금은 {DEFAULT_SOURCE_PREFIX!r} 고정)"
        )


# ---------------------------------------------------------------------------
# 테이블 정의 (data-model §2·§3)
# ---------------------------------------------------------------------------

_ML_STRING = {
    "stack_code",
    "item_code",
    "feature_version",
    "label_version",
    "quality_policy_version",
}
_ML_BOOL = {"feature_valid", "classification_eligible", "regression_eligible"}


def _types():
    from pyspark.sql import types as T

    return T


def silver_schema():
    T = _types()
    double = {"value", "limit", "ratio"}
    fields = []
    for c in [
        "area_nm",
        "fact_manage_nm",
        "stack_code",
        "item",
        "value",
        "limit",
        "status",
        "ts_kst",
        "ratio",
    ]:
        if c == "ts_kst":
            t = T.TimestampNTZType()
        elif c in double:
            t = T.DoubleType()
        else:
            t = T.StringType()
        fields.append(T.StructField(c, t, nullable=c in double))
    return T.StructType(fields)


def ml_ready_schema():
    T = _types()
    fields = []
    for c in ml_ready.COLUMNS:
        if c == "measured_at":
            t = T.TimestampNTZType()
        elif c in _ML_STRING:
            t = T.StringType()
        elif c in _ML_BOOL:
            t = T.BooleanType()
        else:
            t = T.DoubleType()
        fields.append(
            T.StructField(c, t, nullable=c not in {"stack_code", "item_code", "measured_at"})
        )
    return T.StructType(fields)


def table_ddl(table: str, schema, ts_col: str, location: str | None = None) -> str:
    cols = ", ".join(
        f"`{f.name}` {f.dataType.simpleString()}{'' if f.nullable else ' NOT NULL'}"
        for f in schema.fields
    )
    loc = f" LOCATION '{location}'" if location else ""
    return (
        f"CREATE TABLE IF NOT EXISTS {table} ({cols}) USING iceberg "
        f"PARTITIONED BY (days(`{ts_col}`)){loc} TBLPROPERTIES ("
        "'format-version'='2', 'write.distribution-mode'='hash', "
        "'write.parquet.compression-codec'='zstd')"
    )


def table_location(bucket: str, table: str) -> str:
    """`tms_silver2.ktms` → `s3://<bucket>/silver2/ktms` (AGENTS.md: 경로 = 카탈로그 이름)."""
    db, name = table.split(".")
    if not db.startswith("tms_"):
        raise ValueError(f"tms_<층>.<테이블> 형식이어야 한다: {table!r}")
    return f"s3://{bucket}/{db.removeprefix('tms_')}/{name}"


def qualified(table: str) -> str:
    return f"{CATALOG}.{table}"


# ---------------------------------------------------------------------------
# Spark · Iceberg
# ---------------------------------------------------------------------------


def build_spark(app: str):
    """카탈로그 설정은 Glue에서는 잡 인자 `--conf`, 로컬 테스트에서는 fixture가 넣는다."""
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName(app).getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    return spark


def ensure_table(spark, table: str, schema, ts_col: str, location: str | None) -> None:
    spark.sql(table_ddl(qualified(table), schema, ts_col, location))


def to_spark(spark, pdf: pd.DataFrame, schema):
    """pandas → Spark. 스키마 순서로 컬럼을 고르고, 문자열은 object로 둔다(pd.NA → null)."""
    out = pdf[schema.names].copy()
    for f in schema.fields:
        name = f.dataType.typeName()
        if name == "string":
            out[f.name] = out[f.name].astype(object).where(out[f.name].notna(), None)
        elif name == "double":
            out[f.name] = pd.to_numeric(out[f.name], errors="coerce").astype("float64")
        elif name == "boolean":
            out[f.name] = out[f.name].astype(bool)
        else:  # timestamp_ntz
            out[f.name] = pd.to_datetime(out[f.name])
    return spark.createDataFrame(out, schema=schema)


def in_range(pdf: pd.DataFrame, ts_col: str, r: DayRange) -> pd.DataFrame:
    ts = pd.to_datetime(pdf[ts_col])
    return pdf[(ts >= r.start_ts) & (ts < r.end_ts)]


def overwrite_range(
    spark, pdf: pd.DataFrame, schema, table: str, ts_col: str, r: DayRange, props: dict[str, str]
) -> int:
    """대상 범위만 커밋 1번으로 교체하고 새 snapshot_id를 돌려준다(research R5)."""
    from pyspark.sql import functions as F

    pdf = in_range(pdf, ts_col, r)
    if pdf.empty:
        raise ValueError(f"empty result for {r.start}..{r.end}: 쓰지 않는다")
    df = to_spark(spark, pdf, schema)
    writer = df.writeTo(qualified(table))
    for k, v in props.items():
        writer = writer.option(f"snapshot-property.{k}", str(v))
    col = F.col(ts_col)
    writer.overwrite(
        (col >= F.lit(r.start_ts).cast("timestamp_ntz"))
        & (col < F.lit(r.end_ts).cast("timestamp_ntz"))
    )
    snapshot = latest_snapshot_id(spark, table)
    assert snapshot is not None
    return snapshot


def latest_snapshot_id(spark, table: str) -> int | None:
    try:
        rows = spark.sql(
            f"SELECT snapshot_id FROM {qualified(table)}.snapshots "
            "ORDER BY committed_at DESC LIMIT 1"
        ).collect()
    except Exception as exc:  # 테이블이 아직 없음
        if "TABLE_OR_VIEW_NOT_FOUND" in str(exc) or "not found" in str(exc).lower():
            return None
        raise
    return int(rows[0]["snapshot_id"]) if rows else None


def read_range(spark, table: str, ts_col: str, lo: datetime, hi: datetime) -> pd.DataFrame:
    """[lo, hi] 양 끝 포함으로 읽어 pandas로 돌려준다."""
    from pyspark.sql import functions as F

    col = F.col(ts_col)
    df = spark.table(qualified(table)).where(
        (col >= F.lit(lo).cast("timestamp_ntz")) & (col <= F.lit(hi).cast("timestamp_ntz"))
    )
    return df.toPandas()


# ---------------------------------------------------------------------------
# 실행 기록 (contracts/run-interface.md §3)
# ---------------------------------------------------------------------------


def run_record_key(runs_prefix: str, started_at: datetime, job_run_id: str) -> str:
    return f"{runs_prefix.strip('/')}/{started_at.astimezone(UTC):%Y%m%dT%H%M%SZ}_{job_run_id}.json"


def runtime_versions(spark=None) -> dict[str, str]:
    versions = {"python": platform.python_version()}
    if spark is not None:
        versions["spark"] = spark.version
    for name in ("pandas", "numpy"):
        try:
            versions[name] = __import__(name).__version__
        except ImportError:
            versions[name] = "missing"
    return versions


def write_run_record(
    record: dict, bucket: str, key: str, s3=None, local_dir: Path | None = None
) -> str:
    body = json.dumps(record, ensure_ascii=False, indent=2, default=str)
    if local_dir is not None:
        path = Path(local_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return str(path)
    if s3 is None:
        import boto3

        s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="application/json")
    return f"s3://{bucket}/{key}"


def failure_record(base: dict, exc: BaseException) -> dict:
    message = (str(exc).strip().splitlines() or [""])[0][:500]
    return base | {"result": "failed", "error": f"{type(exc).__name__}: {message}"}


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="seconds")
