"""공통 시간 분할에서 모델별 Feature와 Label을 준비한다."""

from contextlib import contextmanager
import hashlib
import json
from math import isfinite
import os
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Literal

import numpy as np
import pandas as pd

from contract import REQUIRED_COLUMNS, validate_contract
from features import FEATURE_COLUMNS, _eligibility_mask
from split import _normalize_times, _time_metadata, _split_masks


def _cgroup_memory() -> dict:
    """현재 Linux 프로세스가 속한 cgroup v1/v2의 사용량·한도를 읽는다."""
    if not sys.platform.startswith("linux"):
        return {"cgroup_status": "not_linux"}
    memberships = []
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        hierarchy, controllers, member = line.split(":", 2)
        if hierarchy == "0" and not controllers:
            memberships.append((2, PurePosixPath(member)))
        elif "memory" in controllers.split(","):
            memberships.append((1, PurePosixPath(member)))
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    for version, member in memberships:
        for line in mounts:
            left, right = line.split(" - ", 1)
            fields, info = left.split(), right.split()
            if not (version == 2 and info[0] == "cgroup2") and not (
                version == 1 and info[0] == "cgroup" and "memory" in info[2].split(",")
            ):
                continue
            root = PurePosixPath(fields[3])
            mount = Path(fields[4].replace("\\040", " ").replace("\\134", "\\"))
            if member == PurePosixPath("/"):
                relative = PurePosixPath(".")
            elif member.is_relative_to(root):
                relative = member.relative_to(root)
            else:
                continue
            directory = mount.joinpath(*relative.parts).resolve()
            if not directory.is_relative_to(mount.resolve()):
                continue
            usage, limit = (("memory.current", "memory.max") if version == 2 else
                            ("memory.usage_in_bytes", "memory.limit_in_bytes"))
            if not (directory / usage).is_file() or not (directory / limit).is_file():
                continue
            raw_limit = (directory / limit).read_text().strip()
            return {"cgroup_status": "ok", "cgroup_version": version,
                    "cgroup_path": str(directory),
                    "cgroup_memory_bytes": int((directory / usage).read_text().strip()),
                    "cgroup_limit_bytes": None if raw_limit == "max" else int(raw_limit),
                    "cgroup_limit_raw": raw_limit}
    return {"cgroup_status": "unavailable"}


def _log_memory(stage: str, *, elapsed_seconds=None, include_cgroup=False) -> None:
    """프로세스 현재·누적 최대 RSS를 바이트 단위로 출력한다. 컨테이너 합계는 아니다."""
    try:
        import psutil

        info = psutil.Process().memory_info()
        if sys.platform.startswith("linux"):
            import resource

            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        else:
            peak = getattr(info, "peak_wset", None)
        record = {"event": "memory", "stage": stage,
                  "rss_bytes": info.rss, "peak_rss_bytes": peak}
    except Exception as exc:
        # 계측 실패는 명시적으로 기록하되 학습 결과에는 영향을 주지 않는다.
        record = {"event": "memory_error", "stage": stage, "reason": str(exc)}
    if elapsed_seconds is not None:
        record["elapsed_seconds"] = elapsed_seconds
    if include_cgroup:
        try:
            record.update(_cgroup_memory())
        except Exception as exc:
            record.update(cgroup_status="unavailable", cgroup_error=str(exc))
    try:
        print(json.dumps(record, ensure_ascii=False), flush=True)
    except Exception:
        # 로그 출력 오류도 학습을 중단시키지 않는다.
        pass


def _update_split_summary(metadata, masks, times):
    for name, mask in masks.items():
        selected = times.loc[mask]
        summary = metadata["splits"][name]
        summary["rows"] += len(selected)
        if not selected.empty:
            summary["start"] = (
                selected.min() if summary["start"] is None
                else min(summary["start"], selected.min())
            )
            summary["end"] = (
                selected.max() if summary["end"] is None
                else max(summary["end"], selected.max())
            )


def _collect_rows(frame, times, metadata, task, pollutant, label, parts):
    """검증 완료 입력만 사용하며 전체 경계 뒤에 물질·적격성을 적용한다."""
    masks = _split_masks(times, metadata)
    _update_split_summary(metadata, masks, times)
    eligible = frame["item_code"].eq(pollutant).fillna(False) & _eligibility_mask(frame, task)
    columns = [*FEATURE_COLUMNS, label, "measured_at"]
    for name, mask in masks.items():
        positions = np.flatnonzero((mask & eligible).to_numpy(dtype=bool))
        if len(positions):
            # 필요한 열과 동일 위치의 Label만 함께 선택한다.
            piece = frame.loc[:, columns].iloc[positions].copy()
            piece["measured_at"] = times.iloc[positions].array
            parts[name].append(piece)


def _finish_datasets(parts, metadata, task, pollutant, label, dtypes, total_rows):
    datasets = {}
    for name, pieces in parts.items():
        if pieces:
            selected = pd.concat(pieces, axis=0, copy=False)
            pieces.clear()
            # 배치·물질 필터 전 원본 순서가 같으면 동시각 행 순서도 보존된다.
            order = selected["measured_at"].argsort(kind="stable")
            selected = selected.iloc[order]
            selected.pop("measured_at")
            # 전체 입력의 pandas dtype을 유지한다. float32 축소 등은 하지 않는다.
            for column in [*FEATURE_COLUMNS, label]:
                if selected[column].dtype != dtypes[column]:
                    selected[column] = selected[column].astype(dtypes[column])
        else:
            selected = pd.DataFrame({
                column: pd.Series(dtype=dtypes[column])
                for column in [*FEATURE_COLUMNS, label]
            })
        y = selected.pop(label)
        valid = y.map(lambda value: pd.notna(value) and isfinite(value))
        if task == "classification":
            valid = valid & y.isin((0, 1))
        if not valid.all():
            positions = np.flatnonzero(~valid.to_numpy(dtype=bool)).tolist()
            raise ValueError(
                f"{name}/{pollutant}: {label} 결측 또는 유효하지 않은 값; "
                f"선택된 구간의 행 위치(0부터): {positions}"
            )
        datasets[name] = {"X": selected, "y": y}
    metadata["excluded_rows"] = total_rows - sum(
        summary["rows"] for summary in metadata["splits"].values()
    )
    metadata["prepared_rows"] = {name: len(value["y"]) for name, value in datasets.items()}
    metadata["has_valid_data"] = {name: not value["y"].empty for name, value in datasets.items()}
    metadata.update(task=task, pollutant=pollutant, label_column=label)
    _log_memory(f"{pollutant}/{task}/data_ready")
    return datasets, metadata


def _new_metadata(start, end):
    metadata = _time_metadata(start, end)
    metadata["splits"] = {
        name: {"start": None, "end": None, "rows": 0}
        for name in ("train", "validation", "test")
    }
    return metadata


@contextmanager
def _parquet_snapshot(path):
    """OS 잠금 없이 검사 시점별 파일 목록·상태·로컬 SHA-256을 비교한다.

    변경 방지 잠금이나 S3 VersionId/ETag 검증은 아니다. 검사 사이에 발생하고
    완전히 복구된 일시 변경까지 배제할 수 없으므로 외부 쓰기 금지가 필요하다.
    파일 복제 없이 고정 크기 버퍼로 해시하며 검증 실패 시 학습 전에 중단한다.
    """
    import pyarrow.dataset as ds

    path = Path(path).resolve(strict=True)

    def signature():
        try:
            current = ds.dataset(str(path), format="parquet", partitioning="hive")
            files = tuple(current.files)
            if not files:
                raise ValueError("Parquet 입력 파일이 없습니다")
            records = tuple(_file_fingerprint(filename) for filename in files)
            # 해시 중 추가·삭제된 파일도 다음 스캔으로 넘기지 않는다.
            after = ds.dataset(str(path), format="parquet", partitioning="hive")
            if tuple(after.files) != files:
                raise ValueError("체크섬 계산 중 입력 파일 목록이 변경됐습니다")
            return records
        except (OSError, ValueError) as exc:
            raise ValueError(f"Parquet 입력 무결성 검증 실패: {path}: {exc}") from exc

    before = signature()
    source = ds.dataset(str(path), format="parquet", partitioning="hive")
    _check_snapshot(tuple(source.files), tuple(record[0] for record in before))

    def check():
        _check_snapshot(signature(), before)

    yield source, check
    check()


def _file_fingerprint(filename):
    """해시를 읽는 동안의 파일 교체·내용 변경도 상태 비교로 검사한다."""
    path = Path(filename)

    def state(info):
        return tuple(getattr(info, field) for field in (
            "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"
        ))

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        before = state(os.fstat(stream.fileno()))
        if state(path.stat()) != before:
            raise ValueError(f"입력 파일이 열기 중 교체됐습니다: {filename}")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        if state(os.fstat(stream.fileno())) != before or state(path.stat()) != before:
            raise ValueError(f"입력 파일이 체크섬 계산 중 변경됐습니다: {filename}")
    return (filename, *before, digest.hexdigest())


def _check_snapshot(current, expected):
    if current != expected:
        raise ValueError("입력 파일 목록·상태 또는 SHA-256이 변경되어 학습을 중단합니다")


def _prepare_parquet(path, task, pollutant, label):
    """전체 35열 검증 스캔 후 모델별 필요한 열만 다시 스캔한다."""
    import pyarrow.dataset as ds

    with _parquet_snapshot(path) as (source, check_snapshot):
        # 파일별 누락을 Dataset의 통합 스키마가 NULL로 숨기지 않게 확인한다.
        for fragment in source.get_fragments():
            physical = fragment.physical_schema
            names = set(physical.names) | set(
                ds.get_partition_keys(fragment.partition_expression)
            )
            missing = set(REQUIRED_COLUMNS) - names
            if missing:
                raise ValueError(f"{fragment.path}: 필수 컬럼 누락: {sorted(missing)}")
            for column in REQUIRED_COLUMNS:
                if column in physical.names and (
                    physical.field(column).type != source.schema.field(column).type
                ):
                    raise ValueError(
                        f"{fragment.path}/{column}: 파일 간 schema가 달라 "
                        "무손실 dtype 동등성을 확인할 수 없습니다"
                    )
        index_specs = (source.schema.pandas_metadata or {}).get("index_columns", [])
        index_columns = [value for value in index_specs if isinstance(value, str)]
        ranges = [value for value in index_specs if isinstance(value, dict)]
        if any(value.get("start") != 0 or value.get("step") != 1 for value in ranges):
            raise ValueError("비표준 Parquet RangeIndex의 기존 행 대응을 확인할 수 없습니다")

        def batches(columns):
            scanner = source.scanner(
                columns=list(dict.fromkeys([*columns, *index_columns])),
                batch_size=65536, batch_readahead=0, fragment_readahead=0,
                use_threads=False,
            )
            offset = 0
            for batch in scanner.to_batches():
                frame = batch.to_pandas()
                if not index_columns:
                    frame.index = pd.RangeIndex(
                        offset, offset + len(frame),
                        name=ranges[0].get("name") if ranges else None,
                    )
                offset += len(frame)
                yield frame

        start = end = None
        dtypes = {}
        total_rows = 0
        for frame in batches(REQUIRED_COLUMNS):
            validate_contract(frame)
            times = _normalize_times(frame["measured_at"], tw_cems_wall_clock=True)
            if not frame.empty:
                start = times.min() if start is None else min(start, times.min())
                end = times.max() if end is None else max(end, times.max())
            total_rows += len(frame)
            for column in [*FEATURE_COLUMNS, label]:
                dtype = frame[column].dtype
                if column in dtypes and dtypes[column] != dtype:
                    # 같은 숫자 열의 NULL 유무에 따른 pandas 승격만 수용한다.
                    try:
                        dtype = np.result_type(dtypes[column], dtype)
                    except TypeError as exc:
                        raise ValueError(f"{column}: 배치 간 dtype 동등성 확인 필요") from exc
                    if dtype.kind not in "iuf":
                        raise ValueError(f"{column}: 배치 간 dtype 동등성 확인 필요")
                dtypes[column] = dtype
        if not total_rows:
            raise ValueError("빈 데이터는 시간순으로 분할할 수 없습니다")
        del frame, times
        check_snapshot()
        metadata = _new_metadata(start, end)
        parts = {name: [] for name in metadata["splits"]}
        columns = [*FEATURE_COLUMNS, label, "measured_at", "item_code",
                   "feature_valid", f"{task}_eligible"]
        second_rows = 0
        for frame in batches(columns):
            times = _normalize_times(frame["measured_at"], tw_cems_wall_clock=True)
            _collect_rows(frame, times, metadata, task, pollutant, label, parts)
            second_rows += len(frame)
        del frame, times
        if second_rows != total_rows:
            raise ValueError("두 스캔의 전체 입력 행 수가 다릅니다")
        check_snapshot()
        result = _finish_datasets(parts, metadata, task, pollutant, label, dtypes, total_rows)
    return result


def prepare_datasets(
    data: pd.DataFrame | str | os.PathLike,
    task: Literal["classification", "regression"],
    pollutant: Literal["nox", "sox"],
) -> tuple[dict[str, dict[str, pd.DataFrame | pd.Series]], dict]:
    """분할별 {'X': DataFrame, 'y': Series}와 공통 분할 메타데이터 반환.

    data는 시나리오 A 대만 CEMS ML-ready 전체 DataFrame 또는 로컬 Parquet 경로다.
    measured_at은 UTC 표기 여부와 관계없이 대만 현지 벽시계로 해석한다.
    Parquet은 불변 입력을 확보한 뒤 전체 검증·시간 경계 스캔과 선택 스캔을 한다.
    적격 행의 Label 결측·무한대 및 분류의 0/1 이외 값은 오류로 알린다.
    원본 인덱스와 행 순서를 보존하며 중복 인덱스로 결합하지 않는다.
    """
    if task not in ("classification", "regression"):
        raise ValueError("task는 classification 또는 regression이어야 합니다")
    if pollutant not in ("nox", "sox"):
        raise ValueError("pollutant는 nox 또는 sox이어야 합니다")

    label = "label_entry_60m" if task == "classification" else "label_ratio_60m"
    if isinstance(data, (str, os.PathLike)):
        return _prepare_parquet(data, task, pollutant, label)
    # 공개 DataFrame 입력은 기존과 같이 전체 계약을 검증한다.
    validate_contract(data)
    if data.empty:
        raise ValueError("빈 데이터는 시간순으로 분할할 수 없습니다")
    times = _normalize_times(data["measured_at"], tw_cems_wall_clock=True)
    metadata = _new_metadata(times.min(), times.max())
    parts = {name: [] for name in metadata["splits"]}
    _collect_rows(data, times, metadata, task, pollutant, label, parts)
    return _finish_datasets(parts, metadata, task, pollutant, label, data.dtypes, len(data))
