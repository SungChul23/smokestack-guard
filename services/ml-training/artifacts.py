"""학습 모델과 호출자가 제공한 평가·메타데이터의 로컬 저장·복원."""

import json
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


def save_artifacts(model, model_id, metrics, metadata, output_dir) -> dict:
    """새 모델 디렉터리에 결과를 저장하고 세 파일의 Path를 반환한다.

    기존 model_id 경로가 있으면 FileExistsError로 중단한다.
    저장 도중 I/O·직렬화 실패 시 오류를 전달하며 부분 결과는 남을 수 있다.
    재시도 시에도 기존 디렉터리를 덮어쓰거나 자동 삭제하지 않는다.
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
    directory.mkdir(parents=True, exist_ok=False)
    paths = {
        "model": directory / "model.joblib",
        "metrics": directory / "metrics.json",
        "metadata": directory / "metadata.json",
    }

    # 배타적 생성 모드로 기존 파일의 덮어쓰기를 한 번 더 방지한다.
    with paths["model"].open("xb") as stream:
        joblib.dump(model, stream, compress=3)
    for name, content in json_contents.items():
        with paths[name].open("x", encoding="utf-8") as stream:
            stream.write(content + "\n")
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
