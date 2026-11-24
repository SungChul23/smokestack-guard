"""N3-C/S3-C 전용 ID로 기존 원자적 저장 구현을 격리 재사용한다."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from v2.config import SCALES

# B 모듈 객체/허용 ID를 바꾸지 않고, 별도 모듈 인스턴스에서 저장 정책만 확장한다.
_spec = spec_from_file_location(
    "_partial_history_artifacts", Path(__file__).resolve().parents[1] / "artifacts.py")
_shared = module_from_spec(_spec)
_spec.loader.exec_module(_shared)
_shared.MODEL_IDS = tuple(SCALES)


def save_artifacts(model, model_id, metrics, metadata, output_dir):
    """기존 3개 파일명·원자적 공개·덮어쓰기 금지를 유지한다."""
    return _shared.save_artifacts(model, model_id, metrics, metadata, output_dir)


def load_model(model_path):
    """직접 저장한 신뢰할 수 있는 모델만 로드한다."""
    return _shared.load_model(model_path)
