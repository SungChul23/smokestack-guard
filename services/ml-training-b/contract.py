"""B 입력 계약과 Feature 화이트리스트 검증. 보간·삭제·플래그 재계산 없음."""
from datetime import datetime
from math import isfinite

import pandas as pd
from pandas.api.types import (
    is_bool, is_bool_dtype, is_complex_dtype, is_datetime64_any_dtype,
    is_number, is_numeric_dtype,
)

if __package__:
    from .config import (FEATURE_COLUMNS, FLAG_COLUMNS, LOAD_COLUMNS,
                         NUMERIC_COLUMNS, STRING_COLUMNS, VERSION_VALUES, check_source)
else:
    from config import (FEATURE_COLUMNS, FLAG_COLUMNS, LOAD_COLUMNS,
                        NUMERIC_COLUMNS, STRING_COLUMNS, VERSION_VALUES, check_source)


def _finite(values: pd.Series) -> pd.Series:
    """혼합 수치형도 값 변경 없이 검사한다."""
    return values.map(lambda v: pd.notna(v) and is_number(v)
                      and not is_bool(v) and not isinstance(v, complex)
                      and isfinite(v))


def validate_contract(data: pd.DataFrame, source: str) -> None:
    """필수 35열과 출처를 검증하고 적격 행의 Feature·정답 오류를 보고한다."""
    check_source(source)
    if not isinstance(data, pd.DataFrame):
        raise TypeError("입력은 pandas.DataFrame이어야 합니다")
    missing = [c for c in LOAD_COLUMNS if c not in data.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing}")
    if data.columns.duplicated().any():
        raise ValueError("중복 컬럼명이 있습니다")
    for c in NUMERIC_COLUMNS:
        series = data[c]
        if is_numeric_dtype(series.dtype) and not (
            is_bool_dtype(series.dtype) or is_complex_dtype(series.dtype)
        ):
            continue
        if not series.dropna().map(
            lambda v: is_number(v) and not is_bool(v) and not isinstance(v, complex)
        ).all():
            raise TypeError(f"{c}: 숫자 자료형이 필요합니다")
    for c in (*STRING_COLUMNS, "data_source"):
        if not data[c].dropna().map(lambda v: isinstance(v, str)).all():
            raise TypeError(f"{c}: 문자열 자료형이 필요합니다")
    for c in FLAG_COLUMNS:
        if not is_bool_dtype(data[c].dtype) and not data[c].dropna().map(is_bool).all():
            raise TypeError(f"{c}: 불리언 자료형이 필요합니다")
    times = data["measured_at"]
    if not is_datetime64_any_dtype(times.dtype) and not times.dropna().map(
        lambda v: isinstance(v, datetime)
    ).all():
        raise TypeError("measured_at: 시간 자료형이 필요합니다")
    if times.isna().any():
        raise ValueError("measured_at에 결측값이 있습니다")
    for c in ("stack_code", "item_code"):
        if data[c].isna().any() or data[c].eq("").any():
            raise ValueError(f"{c}: 결측·빈 식별자가 있습니다")
    if not data["item_code"].isin(("nox", "sox")).all():
        raise ValueError("item_code는 nox 또는 sox여야 합니다")
    for c, value in VERSION_VALUES.items():
        if not data[c].eq(value).fillna(False).all():
            raise ValueError(f"{c}: 모든 행은 {value}이어야 합니다")
    if not data["data_source"].eq(source).fillna(False).all():
        raise ValueError(f"data_source가 요청 출처 {source}와 다릅니다")

    classification = data["classification_eligible"].eq(True).fillna(False)
    regression = data["regression_eligible"].eq(True).fillna(False)
    eligible = classification | regression
    if (eligible & ~data["feature_valid"].eq(True).fillna(False)).any():
        raise ValueError("적격 플래그와 feature_valid가 모순됩니다")
    invalid_features = [c for c in FEATURE_COLUMNS if not _finite(data.loc[eligible, c]).all()]
    if invalid_features:
        raise ValueError(f"적격 행 Feature NaN/Inf 또는 잘못된 수치: {invalid_features}")
    entry = data["label_entry_60m"]
    if not entry.dropna().isin((0, 1)).all():
        raise ValueError("label_entry_60m은 0/1 또는 결측이어야 합니다")
    if not entry.loc[classification].isin((0, 1)).all():
        raise ValueError("분류 적격 행의 Label이 결측 또는 0/1이 아닙니다")
    if not data.loc[classification, "ratio_pct"].lt(90).all():
        raise ValueError("분류 적격 행은 현재 ratio_pct가 90 미만이어야 합니다")
    if not _finite(data.loc[regression, "label_ratio_60m"]).all():
        raise ValueError("회귀 적격 행의 Label에 결측·NaN·Inf가 있습니다")
    # 비적격 행의 결측을 채우지 않으며, 음수·100% 초과 수치는 보존한다.


def select_features(data: pd.DataFrame, source: str) -> pd.DataFrame:
    """검증 후 고정 22열만 선택한다. 행 필터·분할은 후속 단계의 책임이다."""
    validate_contract(data, source)
    return data.loc[:, list(FEATURE_COLUMNS)].copy()
