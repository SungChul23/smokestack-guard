"""K-TMS 테스트용 가짜 데이터 (008). 실제 원본 값은 쓰지 않는다.

`build_silver()`: `ktms.to_silver` 출력과 같은 9컬럼 가짜 Silver.
굴뚝 2개, 항목 `nox`·`sox`·`co`, 2026-11-01 00:00 ~ 11-04 23:30의 30분 격자(KST)다.

| # | 사례 | 위치 |
|---|---|---|
| 1 | 날짜 경계 연속 | 모든 시리즈가 11-02 21:30 ~ 11-03 00:30을 지난다 |
| 2 | 30분 한 칸 공백 | 굴뚝 1 `nox` 11-02 10:30 행 없음 |
| 3 | 진입 1·0, 이미 90% 이상 | 굴뚝 1 `nox` 11-03 22:00~ 85→88→92→95, 11-02 23:00~ 80→82→84 |
| 4 | 기준치 변경 | 굴뚝 2 `sox` 11-03 12:00부터 `limit` 100 → 120 |
| 5 | `status != ok` | 굴뚝 1 `sox` 11-02 05:00 `checking`, 굴뚝 2 `nox` 11-03 08:00 `stopped` |
| 6 | ML 대상 아닌 항목 | 굴뚝 1 `co` (전부 `ok`) |

`snapshot_body`, `put_snapshot`: 수집 원문 형식의 gzip 스냅샷과 `_SUCCESS`를 가짜 S3에 넣는다.
"""

from __future__ import annotations

import gzip
import json
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

SILVER_COLUMNS = [
    "area_nm",
    "fact_manage_nm",
    "stack_code",
    "item",
    "value",
    "limit",
    "status",
    "ts_kst",
    "ratio",
]
STACKS = [("서울특별시", "가나다발전", "001"), ("부산광역시", "라마바소각", "002")]
START = datetime(2026, 11, 1)
SLOTS = 4 * 48  # 11-01 ~ 11-04


def _series_value(stack_i: int, item_i: int, slot: int) -> float:
    return round(50 + 25 * math.sin((slot + 7 * stack_i + 3 * item_i) / 6.0), 2)


def build_silver() -> pd.DataFrame:
    rows = []
    for si, (area, fact, code) in enumerate(STACKS):
        for ii, item in enumerate(["nox", "sox", "co"]):
            if item == "co" and si == 1:
                continue
            for slot in range(SLOTS):
                ts = START + timedelta(minutes=30 * slot)
                value = _series_value(si, ii, slot)
                limit = 100.0
                status = "ok"
                if si == 0 and item == "nox":
                    if ts == datetime(2026, 11, 2, 10, 30):
                        continue  # 2: 한 칸 공백
                    seq = {
                        datetime(2026, 11, 3, 22, 0): 85.0,
                        datetime(2026, 11, 3, 22, 30): 88.0,
                        datetime(2026, 11, 3, 23, 0): 92.0,
                        datetime(2026, 11, 3, 23, 30): 95.0,
                        datetime(2026, 11, 2, 23, 0): 80.0,
                        datetime(2026, 11, 2, 23, 30): 82.0,
                        datetime(2026, 11, 3, 0, 0): 84.0,
                    }
                    value = seq.get(ts, value)
                if si == 1 and item == "sox" and ts >= datetime(2026, 11, 3, 12, 0):
                    limit = 120.0  # 4: 기준치 변경
                if (si == 0 and item == "sox" and ts == datetime(2026, 11, 2, 5, 0)) or (
                    si == 1 and item == "nox" and ts == datetime(2026, 11, 3, 8, 0)
                ):
                    status = "checking" if si == 0 else "stopped"  # 5
                    value = np.nan
                rows.append((area, fact, code, item, value, limit, status, ts))
    df = pd.DataFrame(rows, columns=SILVER_COLUMNS[:-1])
    df["value"] = df["value"].astype("float64")
    df["ratio"] = df["value"] / df["limit"].where(df["limit"] > 0)
    return (
        df[SILVER_COLUMNS]
        .sort_values(["area_nm", "fact_manage_nm", "stack_code", "item", "ts_kst"])
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# 원본 스냅샷
# ---------------------------------------------------------------------------


def stack_item(
    area: str, fact: str, code: str, mesure_dt: str, nox=None, sox=None, limit="100"
) -> dict:
    """수집 원문의 item 하나. 값은 문자열(API와 같다)이고 None이면 키를 null로 둔다."""
    return {
        "area_nm": area,
        "fact_manage_nm": fact,
        "stack_code": code,
        "mesure_dt": mesure_dt,
        "nox_mesure_value": nox,
        "nox_exhst_perm_stdr_value": limit if nox is not None else None,
        "sox_mesure_value": sox,
        "sox_exhst_perm_stdr_value": limit if sox is not None else None,
    }


def snapshot_body(items: list[dict]) -> bytes:
    return gzip.compress(json.dumps({"response": {"body": {"items": items}}}).encode("utf-8"))


def snapshot_folder(run_ts_utc: datetime, prefix: str = "tms_cleansys/") -> str:
    return (
        f"{prefix}ingest_date={run_ts_utc:%Y-%m-%d}/hour={run_ts_utc:%H}/"
        f"run_ts={run_ts_utc:%Y%m%dT%H%M%S}Z"
    )


def put_snapshot(
    s3,
    bucket: str,
    run_ts_utc: datetime,
    items: list[dict],
    success: bool = True,
    prefix: str = "tms_cleansys/",
) -> str:
    folder = snapshot_folder(run_ts_utc, prefix)
    s3.put_object(Bucket=bucket, Key=f"{folder}/snapshot.json.gz", Body=snapshot_body(items))
    if success:
        s3.put_object(Bucket=bucket, Key=f"{folder}/_SUCCESS", Body=b"")
    return folder
