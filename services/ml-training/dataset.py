"""공통 시간 분할에서 모델별 Feature와 Label을 준비한다."""

from math import isfinite
from typing import Literal

import pandas as pd

from contract import validate_contract
from features import select_features
from split import split_by_time


def prepare_datasets(
    data: pd.DataFrame,
    task: Literal["classification", "regression"],
    pollutant: Literal["nox", "sox"],
) -> tuple[dict[str, dict[str, pd.DataFrame | pd.Series]], dict]:
    """분할별 {'X': DataFrame, 'y': Series}와 공통 분할 메타데이터 반환.

    적격 행의 Label 결측·무한대 및 분류의 0/1 이외 값은 오류로 알린다.
    원본 인덱스와 행 순서를 보존하며 중복 인덱스로 결합하지 않는다.
    """
    if task not in ("classification", "regression"):
        raise ValueError("task는 classification 또는 regression이어야 합니다")
    if pollutant not in ("nox", "sox"):
        raise ValueError("pollutant는 nox 또는 sox이어야 합니다")

    # 물질·적격성 필터보다 먼저 전체 입력에서 공통 시간 경계를 계산한다.
    validate_contract(data)
    splits, metadata = split_by_time(data)
    label_column = (
        "label_entry_60m" if task == "classification" else "label_ratio_60m"
    )
    datasets = {}
    prepared_rows = {}
    for name, frame in splits.items():
        pollutant_frame = frame.loc[frame["item_code"].eq(pollutant)]

        # 임시 위치 인덱스로 Feature 선택 결과와 Label을 일대일 대응시킨다.
        # 적격성 계산은 기존 select_features에 맡겨 중복 구현하지 않는다.
        positioned = pollutant_frame.reset_index(drop=True)
        X = select_features(positioned, task)
        y = positioned.iloc[X.index][label_column].copy()

        # 선택된 행의 Label은 조용히 제거하거나 다른 목표로 대체하지 않는다.
        valid = y.map(lambda value: pd.notna(value) and isfinite(value))
        if task == "classification":
            valid = valid & y.isin((0, 1))
        if not valid.all():
            positions = y.index[~valid].tolist()
            raise ValueError(
                f"{name}/{pollutant}: {label_column} 결측 또는 유효하지 않은 값, "
                f"오염물질 필터 후 행 위치(0부터): {positions}"
            )

        # 원본 인덱스는 결과에 복원하되 인덱스 기반 join은 하지 않는다.
        original_index = pollutant_frame.index.take(X.index)
        X.index = original_index
        y.index = original_index
        datasets[name] = {"X": X, "y": y}
        prepared_rows[name] = len(y)

    # 기존 메타데이터의 건수는 전체 입력 기준이며 준비된 적격 행 수는 별도다.
    metadata["prepared_rows"] = prepared_rows
    metadata["task"] = task
    metadata["pollutant"] = pollutant
    metadata["label_column"] = label_column
    return datasets, metadata
