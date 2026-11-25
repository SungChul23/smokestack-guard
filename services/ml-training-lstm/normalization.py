"""LSTM 입력에 Train의 채널 평균과 표준편차만 적용한다."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from adapter import SLOT_COLUMNS

INPUT_SHAPE = (len(SLOT_COLUMNS), 1)


def _checked_input(X: np.ndarray) -> np.ndarray:
    values = np.asarray(X)
    if values.ndim != 3 or values.shape[1:] != INPUT_SHAPE:
        raise ValueError(f"X의 형태는 (batch, {INPUT_SHAPE[0]}, 1)이어야 합니다")
    if values.dtype.kind not in "iuf" or not np.isfinite(values).all():
        raise ValueError("X에는 유한한 실수만 허용합니다")
    return values


@dataclass(frozen=True)
class TrainNormalizer:
    """한 ratio_pct 채널의 Train 통계를 보존한다."""

    mean: float
    scale: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.mean) or not np.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("평균은 유한하고 스케일은 유한한 양수여야 합니다")

    @classmethod
    def from_train(cls, X_train: np.ndarray) -> TrainNormalizer:
        """Train의 모든 행과 6슬롯에 대해 평균과 모집단 표준편차를 계산한다."""
        values = _checked_input(X_train)
        if len(values) == 0:
            raise ValueError("빈 Train에서 정규화 통계를 계산할 수 없습니다")
        mean = float(values.mean(dtype=np.float64))
        std = float(values.std(dtype=np.float64))
        return cls(mean=mean, scale=std if std != 0 else 1.0)

    def transform(self, X: np.ndarray) -> np.ndarray:
        """저장된 통계로 변환하고 Keras 입력용 float32 배열을 반환한다."""
        values = _checked_input(X)
        normalized = ((values.astype(np.float64, copy=False) - self.mean) / self.scale).astype(
            np.float32
        )
        if not np.isfinite(normalized).all():
            raise ValueError("정규화 결과가 float32의 유한한 범위를 벗어났습니다")
        return normalized

    def save(self, path: str | Path) -> None:
        """통계와 슬롯 순서를 JSON으로 저장한다."""
        params = {"mean": self.mean, "scale": self.scale, "slot_columns": list(SLOT_COLUMNS)}
        Path(path).write_text(json.dumps(params, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> TrainNormalizer:
        params = json.loads(Path(path).read_text(encoding="utf-8"))
        if params["slot_columns"] != list(SLOT_COLUMNS):
            raise ValueError("저장된 정규화 통계의 슬롯 순서가 현재 입력과 다릅니다")
        return cls(mean=params["mean"], scale=params["scale"])


def normalize_datasets(datasets: dict) -> tuple[dict, TrainNormalizer]:
    """prepare_datasets 반환값에 연결한다. y와 관측 키는 그대로 전달한다."""
    normalizer = TrainNormalizer.from_train(datasets["train"]["X"])
    normalized = {
        name: {**datasets[name], "X": normalizer.transform(datasets[name]["X"])}
        for name in ("train", "validation", "test")
    }
    return normalized, normalizer
