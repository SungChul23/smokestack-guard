"""학습 모델과 호출자가 제공한 평가·메타데이터의 로컬 저장·복원."""

import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, time
from math import isfinite
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


MODEL_IDS = ("N1-C", "N1-R", "S1-C", "S1-R", "RN1", "RS1")


def _json_value(value):
    """지원 기본 타입만 변환하며 결측·비유한 수치·알 수 없는 타입은 거부한다."""
    if value is pd.NaT or value is pd.NA:
        raise ValueError("JSON에 NaT 또는 pd.NA를 저장할 수 없습니다")
    if isinstance(value, np.datetime64):
        if np.isnat(value):
            raise ValueError("JSON에 NaT를 저장할 수 없습니다")
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        converted = value.item()
        if isinstance(converted, np.generic):
            raise TypeError(f"정밀도 보존 변환을 지원하지 않는 NumPy 타입: {type(value).__name__}")
        return _json_value(converted)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("JSON에 NaN 또는 Infinity를 저장할 수 없습니다")
        return value
    # ISO 8601 표현으로 날짜·시간의 정밀도와 시간대 오프셋을 보존한다.
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON 객체의 키는 문자열이어야 합니다")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(f"JSON 저장을 지원하지 않는 타입: {type(value).__name__}")


def _publish_directory(source: Path, destination: Path) -> None:
    """동일 파일시스템에서 기존 경로를 대체하지 않는 원자적 이동을 수행한다."""
    if os.name == "nt":
        # Windows rename은 목적지가 이미 존재하면 실패한다.
        source.rename(destination)
    elif sys.platform == "linux":
        # 일반 POSIX rename은 빈 디렉터리를 덮어쓸 수 있어 NOREPLACE를 사용한다.
        import ctypes
        import errno

        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise OSError(errno.ENOTSUP, "원자적 비덮어쓰기 renameat2를 지원하지 않습니다")
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(destination))
    else:
        raise NotImplementedError("원자적 비덮어쓰기 저장은 Windows와 Linux에서 지원합니다")


def save_artifacts(model, model_id, metrics, metadata, output_dir) -> dict:
    """새 모델 디렉터리에 결과를 저장하고 세 파일의 Path를 반환한다.

    기존 model_id 경로가 있으면 FileExistsError로 중단한다.
    같은 부모의 임시 디렉터리에 모두 저장한 후 원자적으로 공개한다.
    실패 시 임시 결과만 정리하고 원래 오류를 전달한다. 기존 결과는 유지한다.
    """
    if model_id not in MODEL_IDS:
        raise ValueError(f"지원하지 않는 model_id: {model_id!r}")
    if not isinstance(metrics, dict) or not isinstance(metadata, dict):
        raise TypeError("metrics와 metadata는 dict이어야 합니다")

    # JSON 오류는 디렉터리 생성 전에 확인한다. None과 실제 전달값을 유지한다.
    json_contents = {
        "metrics": json.dumps(_json_value(metrics), ensure_ascii=False, indent=2, allow_nan=False),
        "metadata": json.dumps(_json_value(metadata), ensure_ascii=False, indent=2, allow_nan=False),
    }
    directory = Path(output_dir) / model_id
    if directory.exists() or directory.is_symlink():
        raise FileExistsError(f"기존 모델 결과 경로를 덮어쓸 수 없습니다: {directory}")
    directory.parent.mkdir(parents=True, exist_ok=True)
    paths = {
        "model": directory / "model.joblib",
        "metrics": directory / "metrics.json",
        "metadata": directory / "metadata.json",
    }

    temporary = Path(tempfile.mkdtemp(prefix=f".{model_id}-", dir=directory.parent))
    try:
        with (temporary / "model.joblib").open("xb") as stream:
            joblib.dump(model, stream, compress=3)
        for name, content in json_contents.items():
            with (temporary / paths[name].name).open("x", encoding="utf-8") as stream:
                stream.write(content + "\n")
        _publish_directory(temporary, directory)
    except BaseException as original:
        try:
            shutil.rmtree(temporary)
        except OSError as cleanup_error:
            # 정리 오류가 저장 실패의 원래 예외를 덮어쓰지 않도록 한다.
            original.add_note(f"임시 디렉터리 정리 실패: {temporary}: {cleanup_error}")
        raise
    return paths


def load_model(model_path):
    """직접 저장하고 신뢰할 수 있는 joblib 모델 파일만 불러온다.

    joblib 역직렬화는 코드를 실행할 수 있다. 외부·출처 불명·변조된 파일은
    전달하지 않는다. 이 함수가 파일의 신뢰성을 판별해 주지는 않는다.
    """
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"모델 파일이 없습니다: {path}")
    if not path.is_file():
        raise ValueError(f"모델 경로가 파일이 아닙니다: {path}")
    return joblib.load(path)
