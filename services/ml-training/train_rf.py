"""RN1·RS1 Random Forest 회귀 학습. import만으로 실행하지 않는다."""

from math import isfinite
from os import PathLike
from typing import Literal

import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from dataset import prepare_datasets, _log_memory


def _train_regressor(
    data: pd.DataFrame | str | PathLike,
    pollutant: Literal["nox", "sox"],
    model_name: str,
) -> dict:
    """공통 준비 결과를 검사한 뒤 Train만 학습한다."""
    # 전체 입력의 시간 경계·22개 Feature 순서·회귀 적격성을 그대로 재사용한다.
    datasets, metadata = prepare_datasets(data, task="regression", pollutant=pollutant)
    train = datasets["train"]
    if train["X"].empty:
        raise ValueError(f"{model_name}: 학습 가능한 {pollutant} Train 데이터가 없습니다")

    # RF 전용 정책: 모든 분할의 NaN·무한대를 보고하고 삭제·보간하지 않는다.
    problems = []
    for split_name, dataset in datasets.items():
        X = dataset["X"]
        invalid_columns = [
            column for column in X.columns
            if not X[column].map(
                lambda value: pd.notna(value) and isfinite(value)
            ).all()
        ]
        if invalid_columns:
            problems.append(f"{split_name}: {', '.join(invalid_columns)}")
    if problems:
        raise ValueError(
            f"{model_name}: Feature에 결측값 또는 무한대가 있습니다; "
            + "; ".join(problems)
        )

    # Target은 비율(%) 그대로 사용하며 100% 초과값을 제한하지 않는다.
    # V1.0 실행 최적화 실험: RS1만 CPU 병렬화하고 RN1은 기본값(None)을 유지한다.
    model = RandomForestRegressor(random_state=42, n_jobs=4 if model_name == "RS1" else None)
    _log_memory(f"{model_name}/fit_before")
    model.fit(train["X"], train["y"])
    _log_memory(f"{model_name}/fit_after")
    return {"model": model, "datasets": datasets, "metadata": metadata}


def train_rn1_regressor(data: pd.DataFrame | str | PathLike) -> dict:
    """NOx RN1 모델·분할별 X/y·메타데이터를 반환한다."""
    return _train_regressor(data, pollutant="nox", model_name="RN1")


def train_rs1_regressor(data: pd.DataFrame | str | PathLike) -> dict:
    """SO₂ RS1 모델·분할별 X/y·메타데이터를 반환한다."""
    return _train_regressor(data, pollutant="sox", model_name="RS1")
