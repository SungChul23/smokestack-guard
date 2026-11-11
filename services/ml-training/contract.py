"""
ML-ready 입력의 필수 컬럼과 기본 자료형을 검증한다.
C파트에서 받은 ML-ready 데이터가 약속한 35개 컬럼 구조인지 확인합니다. 잘못된 데이터로 학습하는 일을 방지합니다.
"""

from datetime import datetime

import pandas as pd
from pandas.api.types import (
    is_bool, is_bool_dtype, is_complex_dtype, is_datetime64_any_dtype,
    is_number, is_numeric_dtype,
)


NUMERIC_COLUMNS = (
    "ratio_pct", "headroom_pct", "measure_value", "standard_value",
    "ratio_lag_30m", "ratio_lag_60m", "ratio_lag_90m",
    "ratio_lag_120m", "ratio_lag_150m",
    "ratio_diff_30m", "ratio_diff_60m", "ratio_acceleration",
    "ratio_rolling_mean_1h", "ratio_rolling_mean_3h",
    "ratio_rolling_std_3h", "ratio_rolling_max_3h", "ratio_range_3h",
    "ratio_slope_3h", "rise_count_3h",
    "hour_sin", "hour_cos", "month_sin", "month_cos", "day_of_week",
    "label_entry_60m", "label_ratio_60m",
)
STRING_COLUMNS = (
    "stack_code", "item_code",
    "feature_version", "label_version", "quality_policy_version",
)
FLAG_COLUMNS = (
    "feature_valid", "classification_eligible", "regression_eligible",
)
REQUIRED_COLUMNS = (
    "stack_code", "item_code", "measured_at",
    *NUMERIC_COLUMNS,
    *FLAG_COLUMNS, "feature_version", "label_version", "quality_policy_version",
)

EXPECTED_VERSIONS = {
    "feature_version": "v1",
    "label_version": "v1",
    "quality_policy_version": "v2",
}


def validate_contract(data: pd.DataFrame) -> None:
    """불일치는 컬럼명과 함께 알리고 입력 변환·결측 보완은 수행하지 않는다."""
    # DataFrame과 필수 컬럼을 확인하며 추가 컬럼은 삭제하지 않고 허용한다.
    if not isinstance(data, pd.DataFrame):
        raise TypeError("입력은 pandas.DataFrame이어야 합니다")
    missing = [name for name in REQUIRED_COLUMNS if name not in data.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {', '.join(missing)}")
    duplicates = data.columns[data.columns.duplicated()].intersection(REQUIRED_COLUMNS)
    if len(duplicates):
        raise ValueError(f"필수 컬럼명 중복: {', '.join(duplicates)}")

    # NULL 정책은 미확정이므로 비결측 값의 기본 자료형만 검증한다.
    invalid = []
    for name in NUMERIC_COLUMNS:
        column = data[name]
        if is_numeric_dtype(column.dtype) and not (
            is_bool_dtype(column.dtype) or is_complex_dtype(column.dtype)
        ):
            continue
        if not column.dropna().map(
            lambda value: is_number(value) and not is_bool(value)
            and not isinstance(value, complex)
        ).all():
            invalid.append(f"{name}: 숫자 자료형 필요")
    for name in STRING_COLUMNS:
        if isinstance(data[name].dtype, pd.StringDtype):
            continue
        if not data[name].dropna().map(lambda value: isinstance(value, str)).all():
            invalid.append(f"{name}: 문자 자료형 필요")
    for name in FLAG_COLUMNS:
        if is_bool_dtype(data[name].dtype):
            continue
        if not data[name].dropna().map(is_bool).all():
            invalid.append(f"{name}: 불리언 자료형 필요")

    # 시간 문자열을 자동 변환하지 않고 datetime 자료형 또는 객체를 허용한다.
    times = data["measured_at"]
    if not is_datetime64_any_dtype(times.dtype) and not times.dropna().map(
        lambda value: isinstance(value, datetime)
    ).all():
        invalid.append("measured_at: 시간 자료형 필요")
    if invalid:
        raise TypeError("; ".join(invalid))

    # 확정 버전만 허용하며 버전 결측도 자동 보정하지 않는다.
    for name, expected in EXPECTED_VERSIONS.items():
        if not data[name].eq(expected).fillna(False).all():
            raise ValueError(f"{name}: 모든 행의 버전이 {expected}이어야 합니다")
    # 그 외 세부 dtype·NULL 정책은 변경하지 않는다.

