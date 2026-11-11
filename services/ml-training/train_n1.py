"""NOx의 N1-C·N1-R 학습 함수. import만으로 학습하지 않는다."""

from os import PathLike

import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from dataset import prepare_datasets, _log_memory


def train_n1_classifier(data: pd.DataFrame | str | PathLike) -> dict:
    """N1-C 모델과 분할별 X·y, 분할 메타데이터를 반환한다."""
    # 전체 입력을 전달해 공통 시간 경계를 유지하고 분류 적격 행만 준비한다.
    datasets, metadata = prepare_datasets(data, task="classification", pollutant="nox")
    train = datasets["train"]
    if train["X"].empty:
        raise ValueError("N1-C: 학습 가능한 NOx Train 데이터가 없습니다")
    if not train["y"].isin((0, 1)).all():
        raise ValueError("N1-C: 분류 Label은 0 또는 1이어야 합니다")
    if train["y"].nunique() != 2:
        raise ValueError("N1-C: Train Label에 0과 1이 모두 있어야 합니다")

    # 확정 Feature 순서와 X-y 대응을 그대로 사용한다. 나머지 설정은 기본값이다.
    model = XGBClassifier(random_state=42)
    _log_memory("N1-C/fit_before")
    model.fit(train["X"], train["y"])
    _log_memory("N1-C/fit_after")

    # Validation·Test는 fit에 전달하지 않고 후속 선택·평가용으로 반환한다.
    return {"model": model, "datasets": datasets, "metadata": metadata}


def train_n1_regressor(data: pd.DataFrame | str | PathLike) -> dict:
    """N1-R 모델과 분할별 X·y, 분할 메타데이터를 반환한다."""
    # 회귀 적격 행과 label_ratio_60m을 사용하며 분류 조건을 혼용하지 않는다.
    datasets, metadata = prepare_datasets(data, task="regression", pollutant="nox")
    train = datasets["train"]
    if train["X"].empty:
        raise ValueError("N1-R: 학습 가능한 NOx Train 데이터가 없습니다")

    # 비율(%) Target을 변환·클리핑하지 않아 100% 초과값도 보존한다.
    model = XGBRegressor(random_state=42)
    _log_memory("N1-R/fit_before")
    model.fit(train["X"], train["y"])
    _log_memory("N1-R/fit_after")

    # 실제 학습은 이 함수가 명시적으로 호출될 때만 수행한다.
    return {"model": model, "datasets": datasets, "metadata": metadata}
