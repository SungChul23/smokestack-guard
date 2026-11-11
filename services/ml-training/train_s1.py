"""SO₂의 S1-C·S1-R 학습 함수. import만으로 학습하지 않는다."""

from os import PathLike

import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from dataset import prepare_datasets, _log_memory


def train_s1_classifier(data: pd.DataFrame | str | PathLike) -> dict:
    """S1-C 모델과 분할별 X·y, 분할 메타데이터를 반환한다."""
    # 전체 입력의 공통 시간 경계를 사용하며 SO₂ 분류 적격 행을 준비한다.
    datasets, metadata = prepare_datasets(data, task="classification", pollutant="sox")
    train = datasets["train"]
    if train["X"].empty:
        raise ValueError("S1-C: 학습 가능한 SO₂ Train 데이터가 없습니다")
    if not train["y"].isin((0, 1)).all():
        raise ValueError("S1-C: 분류 Label은 0 또는 1이어야 합니다")
    if train["y"].nunique() != 2:
        raise ValueError("S1-C: Train Label에 0과 1이 모두 있어야 합니다")

    # Feature 순서와 X-y 대응은 공통 모듈에 맡기고 Train만 학습한다.
    model = XGBClassifier(random_state=42)
    _log_memory("S1-C/fit_before")
    model.fit(train["X"], train["y"])
    _log_memory("S1-C/fit_after")
    return {"model": model, "datasets": datasets, "metadata": metadata}


def train_s1_regressor(data: pd.DataFrame | str | PathLike) -> dict:
    """S1-R 모델과 분할별 X·y, 분할 메타데이터를 반환한다."""
    # 회귀 전용 적격 행과 label_ratio_60m을 공통 모듈에서 준비한다.
    datasets, metadata = prepare_datasets(data, task="regression", pollutant="sox")
    train = datasets["train"]
    if train["X"].empty:
        raise ValueError("S1-R: 학습 가능한 SO₂ Train 데이터가 없습니다")

    # 기본 설정으로 비율(%)을 그대로 학습하며 100% 초과값도 보존한다.
    model = XGBRegressor(random_state=42)
    _log_memory("S1-R/fit_before")
    model.fit(train["X"], train["y"])
    _log_memory("S1-R/fit_after")

    # Validation·Test는 fit에 전달하지 않고 후속 선택·평가용으로 반환한다.
    return {"model": model, "datasets": datasets, "metadata": metadata}
