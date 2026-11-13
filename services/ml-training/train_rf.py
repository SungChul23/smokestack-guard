"""RN1·RS1 Random Forest 회귀 학습. import만으로 실행하지 않는다."""

from math import isfinite
from os import PathLike
from contextlib import contextmanager
from threading import Event, Thread
from time import perf_counter
from typing import Literal

import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from dataset import prepare_datasets, _log_memory


@contextmanager
def _monitor_rn1_fit(interval_seconds=15, *, model_name="RN1"):
    """15초 간격으로 계측하며 fit 예외는 그대로 전달한다."""
    started = perf_counter()
    stopped = Event()
    timing = {"monitor_interval_seconds": interval_seconds}

    def sample(stage):
        try:
            _log_memory(stage, elapsed_seconds=perf_counter() - started, include_cgroup=True)
        except Exception:
            # 계측이 실패해도 실제 fit은 계속 수행한다.
            pass

    def monitor():
        while not stopped.wait(interval_seconds):
            sample(f"{model_name}/fit_running")

    sample(f"{model_name}/fit_start")
    thread = Thread(target=monitor, name=f"{model_name.lower()}-memory-monitor", daemon=True)
    try:
        thread.start()
    except Exception:
        thread = None
        sample(f"{model_name}/monitor_start_failed")
    succeeded = False
    try:
        yield timing
        succeeded = True
    finally:
        stopped.set()
        if thread is not None:
            try:
                thread.join(timeout=2)
            except Exception:
                pass
        timing["fit_elapsed_seconds"] = perf_counter() - started
        sample(f"{model_name}/fit_complete" if succeeded else f"{model_name}/fit_failed")


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
    if model_name == "RN1":
        # V1.1 확정 설정. verbose는 완료 작업 수·경과 시간 표시용이다.
        model = RandomForestRegressor(n_estimators=100, max_depth=20,
            min_samples_leaf=1, n_jobs=2, random_state=42, verbose=1)
    else:
        # RS1에도 사용자 확정 V1.1 설정을 적용한다.
        model = RandomForestRegressor(n_estimators=100, max_depth=20,
            min_samples_leaf=1, n_jobs=2, random_state=42, verbose=1)
    _log_memory(f"{model_name}/fit_before")
    with _monitor_rn1_fit(model_name=model_name) as timing:
        model.fit(train["X"], train["y"])
    metadata["model_settings"] = model.get_params(deep=False)
    metadata["experiment"] = {
        "model_version": "V1.1", "experiment_id": f"{model_name}-V1.1-depth20-jobs2",
        "changed_parameters": {"max_depth": 20, "n_jobs": 2},
        "progress_logging": "sklearn/joblib verbose=1 completed tasks and elapsed time",
        **timing,
    }
    _log_memory(f"{model_name}/fit_after")
    return {"model": model, "datasets": datasets, "metadata": metadata}


def train_rn1_regressor(data: pd.DataFrame | str | PathLike) -> dict:
    """NOx RN1 모델·분할별 X/y·메타데이터를 반환한다."""
    return _train_regressor(data, pollutant="nox", model_name="RN1")


def train_rs1_regressor(data: pd.DataFrame | str | PathLike) -> dict:
    """SO₂ RS1 모델·분할별 X/y·메타데이터를 반환한다."""
    return _train_regressor(data, pollutant="sox", model_name="RS1")
