"""Issue #85 SageMaker 학습 설정과 소스 목록을 로컬에서 검토한다."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

REGION = "ap-northeast-2"
INPUT_URI = "s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/"
MODEL_ID = "LN2"
OUTPUT_BUCKET = "sagemaker-ap-northeast-2-952900391026"
OUTPUT_URI = f"s3://{OUTPUT_BUCKET}/LSTM/{MODEL_ID}/"
SOURCE_PREFIX = f"LSTM/{MODEL_ID}/source"
SERVICE = "services/ml-training-lstm"
ENTRY_POINT = f"{SERVICE}/ln2/train_ln2.py"
SOURCE_FILES = (
    f"{SERVICE}/adapter.py",
    f"{SERVICE}/normalization.py",
    f"{SERVICE}/model.py",
    f"{SERVICE}/parquet_stream.py",
    f"{SERVICE}/train_entrypoint.py",
    f"{SERVICE}/ln2/ln2_data.py",
    f"{SERVICE}/ln2/ln2_model.py",
    ENTRY_POINT,
    "src/smokestack_guard/__init__.py",
    "src/smokestack_guard/silver/__init__.py",
    "src/smokestack_guard/silver/ml_ready.py",
)


def _s3_uri(value: str) -> str:
    parsed = urlsplit(value)
    key = parsed.path.strip("/")
    if (
        parsed.scheme != "s3"
        or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", parsed.netloc)
        or not key
        or parsed.query
        or parsed.fragment
        or set(key.split("/")) & {"", ".", ".."}
        or not re.fullmatch(r"[A-Za-z0-9._=/+-]+", key)
    ):
        raise argparse.ArgumentTypeError("s3://bucket/prefix 형식이 필요합니다")
    return f"s3://{parsed.netloc}/{key}/"


def _role_arn(value: str) -> str:
    if not re.fullmatch(r"arn:aws:iam::[0-9]{12}:role/[\w+=,.@/-]+", value, flags=re.ASCII):
        raise argparse.ArgumentTypeError("IAM 실행 Role ARN이 필요합니다")
    return value


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-s3-uri", type=_s3_uri, default=INPUT_URI)
    parser.add_argument("--output-s3-uri", type=_s3_uri, default=OUTPUT_URI)
    parser.add_argument("--role-arn", type=_role_arn)
    parser.add_argument("--training-image")
    parser.add_argument("--instance-type")
    parser.add_argument("--max-run", type=int)
    args = parser.parse_args(argv)

    if not args.output_s3_uri.startswith(OUTPUT_URI):
        parser.error(f"출력 경로는 {OUTPUT_URI} 하위여야 합니다")
    if args.input_s3_uri.startswith(args.output_s3_uri) or args.output_s3_uri.startswith(
        args.input_s3_uri
    ):
        parser.error("입력과 출력 경로가 겹칩니다")
    if args.max_run is not None and args.max_run <= 0:
        parser.error("--max-run은 양의 초 단위 값이어야 합니다")

    source_root = Path(__file__).resolve().parents[3]
    missing = [name for name in SOURCE_FILES if not (source_root / name).is_file()]
    if missing:
        parser.error("학습 소스 누락: " + ", ".join(missing))

    plan = {
        "mode": "review_only",
        "region": REGION,
        "training_job_name_prefix": MODEL_ID,
        "model_id": MODEL_ID,
        "training_image": args.training_image,
        "instance_type": args.instance_type,
        "instance_count": 1,
        "max_runtime_in_seconds": args.max_run,
        "role_arn": args.role_arn,
        "gpu": None,
        "estimated_cost": None,
        "pending_approval": [
            "CPU/GPU 및 인스턴스",
            "학습 이미지와 TensorFlow·PyArrow 환경",
            "실행 Role·실행 시간·예상 비용",
        ],
        # 승인 후 이 목록의 파일만 같은 상대 경로로 묶어 제출한다.
        "source_root": str(source_root),
        "source_upload": {"bucket": OUTPUT_BUCKET, "prefix": SOURCE_PREFIX},
        "source_files": list(SOURCE_FILES),
        "entry_script": ENTRY_POINT,
        "source_archive": "ln2-source.tar.gz",
        "input": {
            "channel_name": "train",
            "input_mode": "File",
            "s3_uri": args.input_s3_uri,
            "environment_variable": "SM_CHANNEL_TRAIN",
        },
        "output": {
            "s3_base_uri": args.output_s3_uri,
            "environment_variable": "SM_MODEL_DIR",
        },
    }
    print(json.dumps(plan, ensure_ascii=True, indent=2))
    return plan


if __name__ == "__main__":
    main()
