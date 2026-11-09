"""ML-ready 테스트용 **가짜** Silver. 실제 원본 값을 쓰지 않는다.

굴뚝·항목 시리즈마다 pandas와 Spark의 차이가 드러나는 사례를 담는다.

| 시리즈 | 사례 |
|---|---|
| F001-P01 nox/sox | 며칠짜리 공백: 11-27 14:00~16:30 → (공백) → 12-01 06:30~10:00 (2023년) |
| F002-P01 nox | 30분 한 칸 공백 (11:00 없음) |
| F003-P01 nox | 월 경계: 2025-09-30 21:00 ~ 2025-10-01 03:00 |
| F004-P01 nox | 라벨: 진입 1(85→88→92), 진입 0(80→82→84), 현재 90% 이상(95) |
| F005-P01 sox | +30만 있고 +60 없음: 80→70→(없음) = null, 80→91→(없음) = 1 |
| 모든 시리즈 | 처음 5슬롯은 feature_valid = false |
| F001-P01 | 고르기에서 빠질 행: status=other_code, item=co, unit=% |
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

SILVER_COLUMNS = [
    "area_nm", "fact_manage_nm", "stack_code", "item", "unit", "value", "limit", "status",
    "ts_kst", "ratio", "ts_local", "code2", "flag_code_ratio_mismatch",
]  # fmt: skip

SLOT = timedelta(minutes=30)


def _series(stack, item, start, pcts, limit=100.0, unit="ppm", status="ok"):
    """pcts[i]가 None이면 그 슬롯은 행이 없다(공백)."""
    rows = []
    for i, pct in enumerate(pcts):
        if pct is None:
            continue
        ts_local = start + i * SLOT
        ratio = pct / 100.0
        rows.append(
            {
                "area_nm": "가짜시",
                "fact_manage_nm": f"가짜사업장{stack[:4]}",
                "stack_code": stack,
                "item": item,
                "unit": unit,
                "value": ratio * limit,
                "limit": limit,
                "status": status,
                "ts_kst": ts_local + timedelta(hours=1),
                "ratio": ratio,
                "ts_local": ts_local,
                "code2": "NA10",
                "flag_code_ratio_mismatch": False,
            }
        )
    return rows


def build_silver() -> pd.DataFrame:
    rows = []
    # 며칠짜리 공백 (2023-11-27 16:30 → 2023-12-01 06:30)
    for item, shift in (("nox", 0.0), ("sox", -20.13)):
        before = [70.21, 72.4, 75.05, 78.33, 80.17, 83.62]
        after = [60.5, 62.25, 61.8, 64.1, 66.73, 65.2, 67.9, 69.44]
        start1, start2 = datetime(2023, 11, 27, 14, 0), datetime(2023, 12, 1, 6, 30)
        rows += _series("F001-P01", item, start1, [p + shift for p in before])
        rows += _series("F001-P01", item, start2, [p + shift for p in after])
    # 고르기에서 빠질 행
    rows += _series("F001-P01", "nox", datetime(2023, 12, 1, 10, 30), [71.0], status="other_code")
    rows += _series("F001-P01", "co", datetime(2023, 12, 1, 6, 30), [40.0, 41.0, 42.0])
    rows += _series("F001-P01", "nox", datetime(2023, 12, 1, 6, 30), [10.0, 11.0], unit="%")
    # 30분 한 칸 공백 (index 2 = 11:00 없음)
    rows += _series(
        "F002-P01", "nox", datetime(2025, 3, 10, 10, 0),
        [55.1, 57.3, None, 58.8, 60.04, 61.9, 59.7, 62.35, 63.1, 64.27],
    )  # fmt: skip
    # 월 경계
    rows += _series(
        "F003-P01", "nox", datetime(2025, 9, 30, 21, 0),
        [40.0, 41.5, 43.25, 42.1, 44.8, 46.3, 45.9, 47.2, 48.65, 50.1, 49.4, 51.75, 53.0],
    )  # fmt: skip
    # 라벨 사례
    rows += _series(
        "F004-P01", "nox", datetime(2025, 5, 1, 0, 0),
        [80.0, 81.2, 82.4, 83.1, 84.6, 85.0, 88.3, 92.7, 80.0, 82.0, 84.0, 86.5, 95.2, 70.8, 72.1],
    )  # fmt: skip
    # +30만 있고 +60 없음
    rows += _series(
        "F005-P01", "sox", datetime(2025, 7, 1, 0, 0),
        [75.0, 76.2, 77.4, 78.1, 79.5, 80.0, 70.0, None, 79.0, 80.5, 81.0, 80.0, 91.0, None, 60.0],
    )  # fmt: skip
    return pd.DataFrame(rows, columns=SILVER_COLUMNS)
