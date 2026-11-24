"""S3.1-C 결과만 허용하는 기존 원자적 저장 구현의 독립 인스턴스."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from s31.config import MODEL_ID

_spec = spec_from_file_location("_s31_artifacts", Path(__file__).resolve().parents[1] / "artifacts.py")
_shared = module_from_spec(_spec)
_spec.loader.exec_module(_shared)
_shared.MODEL_IDS = (MODEL_ID,)


def save_artifacts(model, metrics, metadata, output_dir):
    """중복 모델 폴더를 추가하지 않고 <output_dir>/S3.1-C/의 기존 3파일로 저장한다."""
    return _shared.save_artifacts(model, MODEL_ID, metrics, metadata, output_dir)
