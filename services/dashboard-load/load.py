"""K-TMS 원본 → C의 Silver 규칙 → RDS 적재용 행 (spec 012, research R2).

C의 `read_bronze`·`to_silver`는 수정 없이 부른다. 이 모듈이 더하는 일은
(1) 읽을 원본 범위를 정하고, (2) 굴뚝 키·상태 번호를 붙이고, (3) NOx·SOx만 남기는 것뿐이다.
"""
from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from ktms_pipeline import DayRange, in_range, ingest_dates
from smokestack_guard.silver import ktms

ITEMS = ("nox", "sox")
# ref.status_code와 같은 번호 (migrations/002_ref.sql)
STATUS_CODE = {
    "ok": 0,
    "stopped": 1,
    "checking": 2,
    "no_signal": 3,
    "maintenance": 4,
    "inspection": 5,
    "not_monitored": 8,
    "ambiguous": 9,
    "other": 99,
}
ROW_COLUMNS = [
    "stack_key",
    "item",
    "measured_at",
    "value",
    "limit_value",
    "ratio_pct",
    "status_code",
    "area_nm",
    "fact_manage_nm",
    "stack_code",
]
_RUN_TS = re.compile(r"/run_ts=(\d{8}T\d{6}Z)/")
KST = timedelta(hours=9)


def stack_key(area_nm: pd.Series, fact_manage_nm: pd.Series, stack_code: pd.Series) -> pd.Series:
    """ML-ready의 stack_code와 같은 규칙 (ml_ready.to_ml_ready: 지역|사업장|굴뚝번호)."""
    return area_nm + "|" + fact_manage_nm + "|" + stack_code


# ---------------------------------------------------------------------------
# 읽을 원본 범위
# ---------------------------------------------------------------------------


def run_ts(key: str) -> datetime | None:
    m = _RUN_TS.search(key)
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC) if m else None


class WindowedS3:
    """S3 목록을 수집 시각(run_ts) 창으로 좁힌다. C의 read_bronze는 날짜 단위로만 읽으므로,
    함수를 바꾸지 않고 넘겨주는 클라이언트에서 목록만 거른다. 객체 읽기는 그대로 위임한다."""

    def __init__(self, s3, lo: datetime, hi: datetime):
        self._s3, self.lo, self.hi = s3, lo, hi

    def get_object(self, **kwargs):
        return self._s3.get_object(**kwargs)

    def get_paginator(self, name: str):
        inner = self._s3.get_paginator(name)
        outer = self

        class _Pager:
            def paginate(self, **kwargs):
                for page in inner.paginate(**kwargs):
                    contents = [o for o in page.get("Contents", []) if outer._keep(o["Key"])]
                    yield {**page, "Contents": contents}

        return _Pager()

    def _keep(self, key: str) -> bool:
        ts = run_ts(key)
        return ts is not None and self.lo <= ts < self.hi


def recent_window(now: datetime, hours: float) -> tuple[datetime, datetime]:
    """수집 시각 기준 [now − hours, now). 측정 시각으로는 거르지 않는다(FR-005)."""
    if hours <= 0 or hours > 48:
        raise ValueError(f"hours는 0보다 크고 48 이하여야 한다: {hours}")
    now = now.astimezone(UTC)
    return now - timedelta(hours=hours), now


def ingest_span(lo: datetime, hi: datetime) -> tuple[date, date]:
    """창이 걸친 UTC 수집일 (원본 폴더 ingest_date는 UTC)."""
    return lo.astimezone(UTC).date(), (hi - timedelta(microseconds=1)).astimezone(UTC).date()


def day_range(day: date, now: datetime) -> DayRange:
    """다시 채우기 하루. 진행 중인 오늘(KST)과 미래는 받지 않는다."""
    today_kst = (now.astimezone(UTC) + KST).date()
    if day > today_kst:
        raise ValueError(f"미래 날짜는 채울 수 없다: {day}")
    return DayRange(day, day)


# ---------------------------------------------------------------------------
# 읽기 + C의 규칙
# ---------------------------------------------------------------------------


def _to_silver(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=[*ktms.STACK, "item", "value", "limit", "status", "ts_kst", "ratio"])
    return ktms.to_silver(raw)


def read_recent(bucket: str, now: datetime, hours: float, s3) -> tuple[pd.DataFrame, dict]:
    lo, hi = recent_window(now, hours)
    start, end = ingest_span(lo, hi)
    raw = ktms.read_bronze(bucket, start, end, s3=WindowedS3(s3, lo, hi))
    info = {
        "ingest_from": lo.isoformat(),
        "ingest_to": hi.isoformat(),
        "snapshots": int(raw["snapshot"].nunique()) if not raw.empty else 0,
    }
    return _to_silver(raw), info


def read_day(bucket: str, day: date, now: datetime, s3) -> tuple[pd.DataFrame, dict]:
    """008과 같은 원본 범위(ingest_dates)로 읽어 그 KST 날짜만 남긴다 → 확정된 날은 Silver와 같다."""
    r = day_range(day, now)
    start, end = ingest_dates(r, now)
    raw = ktms.read_bronze(bucket, start, end, s3=s3)
    silver = _to_silver(raw)
    info = {
        "ingest_dates": [start.isoformat(), end.isoformat()],
        "snapshots": int(raw["snapshot"].nunique()) if not raw.empty else 0,
    }
    return (in_range(silver, "ts_kst", r) if not silver.empty else silver), info


# ---------------------------------------------------------------------------
# 적재용 정리
# ---------------------------------------------------------------------------


def prepare_rows(silver: pd.DataFrame) -> pd.DataFrame:
    """Silver 행 → obs.measurement_30m 행 (+ 새 굴뚝 등록용 원본 식별 3개).

    측정값이 없으면 value는 비워 둔다. 0으로 채우지 않는다(FR-003).
    """
    df = silver[silver["item"].isin(ITEMS)]
    if df.empty:
        return pd.DataFrame(columns=ROW_COLUMNS)
    unknown = sorted(set(df["status"]) - set(STATUS_CODE))
    if unknown:
        raise ValueError(f"ref.status_code에 없는 상태: {unknown} (C의 Silver 계약과 다름)")
    out = pd.DataFrame(
        {
            "stack_key": stack_key(df["area_nm"], df["fact_manage_nm"], df["stack_code"]),
            "item": df["item"],
            "measured_at": pd.to_datetime(df["ts_kst"]),
            "value": pd.to_numeric(df["value"], errors="coerce"),
            "limit_value": pd.to_numeric(df["limit"], errors="coerce"),
            "ratio_pct": pd.to_numeric(df["ratio"], errors="coerce") * 100,
            "status_code": df["status"].map(STATUS_CODE).astype("int16"),
            "area_nm": df["area_nm"],
            "fact_manage_nm": df["fact_manage_nm"],
            "stack_code": df["stack_code"],
        }
    )
    dup = out.duplicated(["stack_key", "item", "measured_at"])
    if dup.any():  # to_silver가 키마다 하나만 남기므로 생기면 안 된다
        raise ValueError(f"같은 키가 {int(dup.sum())}개 중복됨")
    return out.reset_index(drop=True)
