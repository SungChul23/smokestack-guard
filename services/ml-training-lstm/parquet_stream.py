"""로컬 대만 CEMS Parquet을 배치로 읽는 LSTM 입력 경로."""
from __future__ import annotations

from collections.abc import Iterator
from math import sqrt
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from adapter import FLAGS, LABEL, PERIODS, SLOT_COLUMNS, VERSIONS, prepare_datasets
from normalization import TrainNormalizer

_COLUMNS = ("stack_code", "item_code", "measured_at", *SLOT_COLUMNS, LABEL, *FLAGS, *VERSIONS)


class ParquetStream:
    """고정 파일 목록을 매 순회 다시 열어 전체 적격 행을 전달한다."""

    def __init__(self, path: str | Path, *, read_batch_size: int = 65536) -> None:
        if "://" in str(path):
            raise ValueError("로컬 Parquet 파일 또는 폴더 경로가 필요합니다")
        if isinstance(read_batch_size, bool) or not isinstance(read_batch_size, int) or read_batch_size <= 0:
            raise ValueError("read_batch_size는 양의 정수여야 합니다")
        self._input = Path(path).absolute()
        self._read_batch_size = read_batch_size
        self._manifest = self._snapshot()

    def _snapshot(self) -> tuple[dict, ...]:
        if self._input.is_file() and self._input.suffix.lower() == ".parquet":
            paths = (self._input,)
        elif self._input.is_dir():
            paths = tuple(sorted(p for p in self._input.rglob("*.parquet") if p.is_file()))
        else:
            paths = ()
        if not paths:
            raise ValueError(f"로컬 Parquet 입력 파일이 없습니다: {self._input}")
        manifest = []
        for path in paths:
            state = path.stat()
            manifest.append({
                "path": str(path),
                "size_bytes": state.st_size,
                "mtime_ns": state.st_mtime_ns,
                "ctime_ns": state.st_ctime_ns,
                "device": state.st_dev,
                "inode": state.st_ino,
            })
        return tuple(manifest)

    @property
    def manifest(self) -> list[dict]:
        """읽은 파일의 목록과 메타데이터를 반환한다."""
        return [entry.copy() for entry in self._manifest]

    def _check_input(self) -> None:
        if self._snapshot() != self._manifest:
            raise RuntimeError("Parquet 파일 목록 또는 메타데이터가 변경되었습니다")

    def _iter_datasets(self) -> Iterator[dict]:
        self._check_input()
        for entry in self._manifest:
            with pq.ParquetFile(entry["path"]) as source:
                names = source.schema_arrow.names
                missing = set(_COLUMNS).difference(names)
                if missing:
                    raise ValueError(f"{entry['path']}: 필수 컬럼 누락: {sorted(missing)}")
                columns = [*_COLUMNS]
                if "data_source" in names:
                    columns.append("data_source")
                for batch in source.iter_batches(
                    batch_size=self._read_batch_size, columns=columns, use_threads=False
                ):
                    yield prepare_datasets(batch.to_pandas())
        self._check_input()

    def scan(self) -> tuple[TrainNormalizer, dict]:
        """전체 분할 건수와 Train 전체 슬롯의 모집단 평균·표준편차를 구한다."""
        counts = {name: {"rows": 0, "positive": 0} for name in PERIODS}
        count = 0
        mean = 0.0
        m2 = 0.0
        for datasets in self._iter_datasets():
            for name, part in datasets.items():
                counts[name]["rows"] += len(part["y"])
                counts[name]["positive"] += int(part["y"].sum())
            slots = datasets["train"]["X"]
            if slots.size:
                batch_count = slots.size
                batch_mean = float(np.mean(slots, dtype=np.float64))
                batch_m2 = float(np.var(slots, dtype=np.float64)) * batch_count
                # 배치 간 평균 차이를 보정하여 Train 전체의 제곱합을 합친다.
                delta = batch_mean - mean
                combined = count + batch_count
                m2 += batch_m2 + delta * delta * (count * batch_count / combined)
                mean += delta * (batch_count / combined)
                count = combined
        if not count:
            raise ValueError("빈 Train에서 정규화 통계를 계산할 수 없습니다")
        scale = sqrt(m2 / count)
        return TrainNormalizer(mean, scale or 1.0), counts

    def iter_split(self, split: str) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """하나의 분할에 속한 X·y를 파일과 배치의 순서로 전달한다."""
        if split not in PERIODS:
            raise ValueError(f"알 수 없는 분할: {split}")
        for datasets in self._iter_datasets():
            part = datasets[split]
            if len(part["y"]):
                yield part["X"], part["y"]
