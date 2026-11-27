"""LN2 전용 Feature 계약과 배치 정규화."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from adapter import PERIODS, SLOT_COLUMNS, _taipei_times, prepare_datasets
from normalization import TrainNormalizer
from parquet_stream import ParquetStream, _COLUMNS

STAT_COLUMNS = (
    "ratio_rolling_max_3h", "ratio_rolling_std_3h",
    "ratio_slope_3h", "ratio_acceleration",
)
TIME_COLUMNS = ("hour_sin", "hour_cos", "month_sin", "month_cos")
FEATURE_COLUMNS = STAT_COLUMNS + TIME_COLUMNS
KEYS = ["stack_code", "item_code", "measured_at"]


def prepare_fusion_batch(frame: pd.DataFrame) -> dict:
    """LN1과 같은 행을 고르고 정렬된 관측 키로 추가 Feature를 연결한다."""
    missing = set(FEATURE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"LN2 Feature 누락: {sorted(missing)}")
    parts = prepare_datasets(frame)
    keys = frame.loc[:, KEYS].assign(measured_at=_taipei_times(frame.measured_at))
    index = pd.MultiIndex.from_frame(keys)
    if not index.is_unique:
        raise ValueError("중복 굴뚝·물질·측정 시각")
    for part in parts.values():
        positions = index.get_indexer(pd.MultiIndex.from_frame(part["rows"]))
        if (positions < 0).any():
            raise ValueError("LN2 Feature와 관측 키 연결 실패")
        features = frame.loc[:, list(FEATURE_COLUMNS)].iloc[positions].to_numpy(
            dtype=np.float64, na_value=np.nan
        )
        if not np.isfinite(features).all():
            raise ValueError("LN1 적격 행의 LN2 Feature에 NaN 또는 Inf가 있습니다")
        part["X"] = (part["X"], features)
    return parts


@dataclass(frozen=True)
class FusionNormalizer:
    sequence: TrainNormalizer
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]

    def __post_init__(self) -> None:
        mean, scale = np.asarray(self.feature_mean), np.asarray(self.feature_scale)
        if mean.shape != (len(STAT_COLUMNS),) or scale.shape != mean.shape:
            raise ValueError("통계 Feature 정규화 파라미터 수가 다릅니다")
        if not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale <= 0).any():
            raise ValueError("통계 Feature 정규화 파라미터가 유효하지 않습니다")

    def transform(self, X: tuple[np.ndarray, np.ndarray]) -> dict[str, np.ndarray]:
        sequence, features = X
        if features.shape != (len(sequence), len(FEATURE_COLUMNS)) or not np.isfinite(features).all():
            raise ValueError("LN2 Feature 행 수·형태 또는 유한값 계약 불일치")
        normalized = features.astype(np.float32, copy=True)
        width = len(STAT_COLUMNS)
        normalized[:, :width] = (features[:, :width] - self.feature_mean) / self.feature_scale
        if not np.isfinite(normalized).all():
            raise ValueError("LN2 Feature 변환 결과가 유한하지 않습니다")
        return {"sequence": self.sequence.transform(sequence), "features": normalized}

    def save(self, path: str | Path) -> None:
        payload = {
            "sequence": {"slot_columns": SLOT_COLUMNS, "mean": self.sequence.mean, "scale": self.sequence.scale},
            "statistics": {"columns": STAT_COLUMNS, "mean": self.feature_mean, "scale": self.feature_scale},
            "passthrough_columns": TIME_COLUMNS,
        }
        Path(path).write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> FusionNormalizer:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        sequence, stats = payload["sequence"], payload["statistics"]
        if (tuple(sequence["slot_columns"]) != SLOT_COLUMNS
                or tuple(stats["columns"]) != STAT_COLUMNS
                or tuple(payload["passthrough_columns"]) != TIME_COLUMNS):
            raise ValueError("LN2 정규화 JSON의 컬럼 순서가 다릅니다")
        return cls(TrainNormalizer(sequence["mean"], sequence["scale"]),
                   tuple(stats["mean"]), tuple(stats["scale"]))


class _Moments:
    """배치 간 평균과 제곱 편차 합을 결합한다."""
    def __init__(self) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, values: np.ndarray) -> None:
        n = len(values)
        if not n:
            return
        mean = values.mean(axis=0, dtype=np.float64)
        delta = mean - self.mean
        total = self.count + n
        self.m2 = self.m2 + values.var(axis=0, dtype=np.float64) * n + delta**2 * (self.count * n / total)
        self.mean = self.mean + delta * (n / total)
        self.count = total

    def scale(self) -> np.ndarray:
        std = np.sqrt(self.m2 / self.count)
        return np.where(std == 0, 1.0, std)


class FusionStream(ParquetStream):
    """LN1의 로컬 파일 스냅샷 검사와 분할 순회를 재사용한다."""
    def _iter_datasets(self):
        self._check_input()
        required = (*_COLUMNS, *FEATURE_COLUMNS)
        for entry in self._manifest:
            with pq.ParquetFile(entry["path"]) as source:
                names = source.schema_arrow.names
                missing = set(required).difference(names)
                if missing:
                    raise ValueError(f"{entry['path']}: 필수 컬럼 누락: {sorted(missing)}")
                columns = [*required]
                if "data_source" in names:
                    columns.append("data_source")
                for batch in source.iter_batches(
                    batch_size=self._read_batch_size, columns=columns, use_threads=False
                ):
                    yield prepare_fusion_batch(batch.to_pandas())
        self._check_input()

    def scan(self) -> tuple[FusionNormalizer, dict]:
        counts = {name: {"rows": 0, "positive": 0} for name in PERIODS}
        sequence, statistics = _Moments(), _Moments()
        for parts in self._iter_datasets():
            for name, part in parts.items():
                counts[name]["rows"] += len(part["y"])
                counts[name]["positive"] += int(part["y"].sum())
            X, Z = parts["train"]["X"]
            sequence.update(X.reshape(-1))
            statistics.update(Z[:, :len(STAT_COLUMNS)])
        if not sequence.count:
            raise ValueError("빈 Train에서 LN2 정규화 통계를 계산할 수 없습니다")
        stats = FusionNormalizer(
            TrainNormalizer(float(sequence.mean), float(sequence.scale())),
            tuple(float(x) for x in statistics.mean),
            tuple(float(x) for x in statistics.scale()),
        )
        return stats, counts
