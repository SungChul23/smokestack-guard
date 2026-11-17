"""추론용 Feature: Silver 최근 슬롯만으로 학습(ML-ready)과 같은 규칙의 Feature를 계산한다.

학습 테이블은 매일 03:00에 최근 2일을 다시 계산하고 라벨이 확정돼야 쓸 수 있어서 최신 값에는 부적합하다.
여기서는 `to_ml_ready`를 그대로 불러 Feature 규칙이 학습과 어긋나지 않게 하고, 라벨 대신 `inference_eligible`만 붙인다.

- 입력: Silver 행(`to_ml_ready`가 받는 형식), 최근 `MIN_HISTORY_HOURS`시간 이상. 기준치(`standard_value`) 존재는 Silver의 `ok` 조건이
  보장한다(대만 `tw_cems.py`, K-TMS `ktms.py`가 기준치 없는 행을 `not_monitored`로 내린다). 이미 ML-ready 형태인 입력에
  `standard_value`가 없으면 기준치 불변으로 판정되므로(학습의 `limit_changed`와 같은 동작) Silver 행만 넣는다. 24시간 이력 피처나 최소 관측 수 규칙을 쓰게 되면 윈도를 24시간 이상으로 늘린다.
- 출력: `as_of`(기본은 입력의 가장 최근 슬롯) 시각 행만, 굴뚝·항목당 1행. 그 시각에 값이 없는 굴뚝은 나오지 않는다.
- `inference_eligible` = 최근 6슬롯이 모두 관측(`feature_valid`) AND 그 150분 동안 기준치(limit)가 바뀌지 않음.
  학습의 `limit_changed`는 60분 뒤까지 보지만 추론 시점에는 미래가 없어서 과거 구간만 본다.
"""
from __future__ import annotations

import pandas as pd

from smokestack_guard.silver.ml_ready import COLUMNS, WINDOW, to_ml_ready

SLOT_MINUTES = 30
MIN_HISTORY_HOURS = WINDOW * SLOT_MINUTES / 60  # 3시간: 6슬롯(현재 포함)
LABEL_COLUMNS = {"label_entry_60m", "label_ratio_60m", "classification_eligible", "regression_eligible"}
INFERENCE_COLUMNS = [c for c in COLUMNS if c not in LABEL_COLUMNS] + ["inference_eligible"]


def to_inference_features(df: pd.DataFrame, as_of=None, data_source: str | None = None) -> pd.DataFrame:
    out = to_ml_ready(df, data_source=data_source)
    if out.empty:
        return pd.DataFrame(columns=INFERENCE_COLUMNS)
    out = out.sort_values(["stack_code", "item_code", "measured_at"]).reset_index(drop=True)
    sv = out.groupby(["stack_code", "item_code"], sort=False)["standard_value"]
    spread = sv.rolling(WINDOW, min_periods=1).max().reset_index(level=[0, 1], drop=True) - sv.rolling(WINDOW, min_periods=1).min().reset_index(level=[0, 1], drop=True)
    out["inference_eligible"] = out["feature_valid"].astype(bool) & spread.fillna(0).le(0)
    as_of = out["measured_at"].max() if as_of is None else pd.Timestamp(as_of)
    return out[out["measured_at"] == as_of][INFERENCE_COLUMNS].reset_index(drop=True)
