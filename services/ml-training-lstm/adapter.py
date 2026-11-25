"""Issue #85의 대만 CEMS NOx 완전 이력 입력 어댑터."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

from smokestack_guard.silver.ml_ready import (
    FEATURE_VERSION,
    LABEL_VERSION,
    LAGS,
    QUALITY_POLICY_VERSION,
)

SLOT_COLUMNS = tuple(f"ratio_lag_{minutes}m" for minutes in reversed(LAGS)) + ("ratio_pct",)
LABEL = "label_entry_60m"
FLAGS = ("feature_valid", "classification_eligible")
VERSIONS = {
    "feature_version": FEATURE_VERSION,
    "label_version": LABEL_VERSION,
    "quality_policy_version": QUALITY_POLICY_VERSION,
}
PERIODS = {
    "train": ("2023-11-01", "2025-11-01"),
    "validation": ("2025-11-01", "2026-05-01"),
    "test": ("2026-05-01", "2026-11-01"),
}
TIMEZONE = "Asia/Taipei"
EMBARGO = pd.Timedelta(minutes=60)


def _taipei_times(raw: pd.Series) -> pd.Series:
    """대만 CEMS의 UTC 표기는 현지 벽시계 시각으로 해석한다."""
    if is_numeric_dtype(raw.dtype) or is_bool_dtype(raw.dtype):
        raise ValueError("measured_at은 날짜와 시각이어야 합니다")
    times = pd.to_datetime(raw, errors="raise")
    zone = times.dt.tz
    if zone is not None and str(zone) not in {"UTC", "Etc/UTC", TIMEZONE}:
        raise ValueError("대만 CEMS 계약에 없는 시간대입니다")
    times = times.dt.tz_localize(None).dt.tz_localize(TIMEZONE)
    if times.isna().any() or times.ne(times.dt.floor("30min")).any():
        raise ValueError("measured_at은 결측 없는 30분 슬롯이어야 합니다")
    return times


def prepare_datasets(data: pd.DataFrame) -> dict[str, dict[str, np.ndarray | pd.DataFrame]]:
    """Train/Validation/Test별 X (n, 6, 1), y (n,), 대응하는 관측 키를 반환한다.

    정규화된 대만 ML-ready 행의 저장된 Lag와 Label을 사용한다.
    빈 분할에도 같은 반환 형태를 유지한다. 동일 시각은 원본 입력 순서를 따른다.
    """
    
    if not isinstance(data, pd.DataFrame):
        raise TypeError("ML-ready pandas DataFrame이 필요합니다")
    keys = ["stack_code", "item_code", "measured_at"]
    required = {*keys, *SLOT_COLUMNS, LABEL, *FLAGS, *VERSIONS}
    missing = required.difference(data.columns)
    if missing or not data.columns.is_unique:
        raise ValueError(f"필수 컬럼 누락 또는 중복 이름: {sorted(missing)}")
    for column, expected in VERSIONS.items():
        if not data[column].eq(expected).fillna(False).all():
            raise ValueError(f"{column}은 {expected}여야 합니다")
    if "data_source" in data and not data["data_source"].eq("tw_cems").fillna(False).all():
        raise ValueError("대만 CEMS 데이터만 입력할 수 있습니다")
    for column in FLAGS:
        if not is_bool_dtype(data[column].dtype) and not data[column].dropna().map(
            lambda value: isinstance(value, (bool, np.bool_))
        ).all():
            raise ValueError(f"{column}은 불리언이어야 합니다")
    for column in (*SLOT_COLUMNS, LABEL):
        dtype = data[column].dtype
        if data[column].notna().any() and (
            not is_numeric_dtype(dtype) or is_bool_dtype(dtype) or is_complex_dtype(dtype)
        ):
            raise ValueError(f"{column}은 실수형 수치 컬럼이어야 합니다")

    times = _taipei_times(data["measured_at"])
    start = pd.Timestamp(PERIODS["train"][0], tz=TIMEZONE)
    end = pd.Timestamp(PERIODS["test"][1], tz=TIMEZONE)
    if (times.lt(start) | times.ge(end)).any():
        raise ValueError("관측 시각이 확정된 대만 36개월 범위를 벗어났습니다")
    eligible = data["item_code"].eq("nox")
    for flag in FLAGS:
        eligible &= data[flag].eq(True)
    candidates = np.flatnonzero(eligible.fillna(False).to_numpy(dtype=bool))
    slots = data.loc[:, list(SLOT_COLUMNS)].iloc[candidates].to_numpy(
        dtype=np.float64, na_value=np.nan
    )
    finite = np.isfinite(slots).all(axis=1)
    positions = candidates[finite]
    slots = slots[finite]
    y = data[LABEL].iloc[positions]
    if not y.isin((0, 1)).all():
        raise ValueError("적격 행의 label_entry_60m은 0 또는 1이어야 합니다")
    labels = y.to_numpy(dtype=np.int64)
    timestamps = times.iloc[positions]

    order = timestamps.argsort(kind="stable").to_numpy()
    positions, slots, labels = positions[order], slots[order], labels[order]
    timestamps = timestamps.iloc[order]
    # 기존 A 공통 분할과 동일한 [start, end) 및 Train/Validation 말미 60분 제외.
    datasets = {}
    for split, (begin, stop) in PERIODS.items():
        lower = pd.Timestamp(begin, tz=TIMEZONE)
        upper = pd.Timestamp(stop, tz=TIMEZONE)
        if split != "test":
            upper -= EMBARGO
        selected = (timestamps.ge(lower) & timestamps.lt(upper)).to_numpy()
        rows = data.loc[:, keys].iloc[positions[selected]].copy()
        rows["measured_at"] = timestamps.iloc[selected].array
        datasets[split] = {
            "X": slots[selected, :, np.newaxis],
            "y": labels[selected],
            "rows": rows.reset_index(drop=True),
        }
    return datasets
