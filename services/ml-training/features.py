"""
기존 적격 플래그로 행을 선택하고 학습 Feature만 반환한다.
35개 컬럼 중 실제 모델에 사용할 22개만 추출하고, 학습 가능한 행을 선택합니다.
"""

from typing import Literal

import pandas as pd

from contract import validate_contract


# 사용자 확정 순서이며 원본 ppm·기준치·식별·Label·품질·버전은 제외한다.
FEATURE_COLUMNS = (
    "ratio_pct", "headroom_pct",
    "ratio_lag_30m", "ratio_lag_60m", "ratio_lag_90m",
    "ratio_lag_120m", "ratio_lag_150m",
    "ratio_diff_30m", "ratio_diff_60m", "ratio_acceleration",
    "ratio_rolling_mean_1h", "ratio_rolling_mean_3h",
    "ratio_rolling_std_3h", "ratio_rolling_max_3h", "ratio_range_3h",
    "ratio_slope_3h", "rise_count_3h",
    "hour_sin", "hour_cos", "month_sin", "month_cos", "day_of_week",
)


def _eligibility_mask(data: pd.DataFrame, task: str) -> pd.Series:
    """검증된 내부 입력에서 기존 플래그의 참 여부만 선택한다."""
    return (
        data["feature_valid"].eq(True) & data[f"{task}_eligible"].eq(True)
    ).fillna(False)


def select_features(
    data: pd.DataFrame,
    task: Literal["classification", "regression"],
) -> pd.DataFrame:
    """계약 검증 후 목적별 적격 행의 22개 Feature를 고정 순서로 복사한다."""
    if task not in ("classification", "regression"):
        raise ValueError("task는 classification 또는 regression이어야 합니다")
    validate_contract(data)

    # 참으로 확인된 행만 선택한다. NULL 플래그는 적격으로 간주하지 않는다.
    eligible = _eligibility_mask(data, task)
    # 원본 인덱스·결측값을 유지하고 입력 데이터나 기존 플래그를 변경하지 않는다.
    return data.loc[eligible, list(FEATURE_COLUMNS)].copy()
