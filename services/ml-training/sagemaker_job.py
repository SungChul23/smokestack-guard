"""SDK 3.x 단일 모델 Training Job 설정. 기본 실행은 AWS 없는 설정 출력이다.

API 근거: https://sagemaker.readthedocs.io/en/stable/training/
이미지 근거: https://aws.github.io/deep-learning-containers/reference/available_images/
서울 레지스트리: https://aws.github.io/deep-learning-containers/reference/region_availability/
--submit은 실제 비용이 발생하는 제출이므로 사용자 승인 후에만 사용한다.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


REGION = "ap-northeast-2"
INSTANCE_TYPE = "ml.r5.2xlarge"
INSTANCE_COUNT = 1
DEFAULT_MAX_RUN = 3600
MODEL_IDS = ("N1-C", "N1-R", "S1-C", "S1-R", "RN1", "RS1")
MODEL_VERSIONS = {model_id: ("1.1" if model_id in ("RN1", "RS1") else "1.0")
                  for model_id in MODEL_IDS}


def _job_identity(model_id, now=None, *, model_version=None):
    """모델별 버전 설정으로 이름·태그를 함께 만든다. 시각은 UTC다."""
    version = model_version or MODEL_VERSIONS[model_id]
    if not re.fullmatch(r"\d+\.\d+", version):
        raise ValueError("모델 버전은 major.minor 형식이어야 합니다")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S-%f")
    name = f"e-ml-{model_id.lower()}-v{version.replace('.', '-')}-{stamp}"
    if len(name) > 63:
        raise ValueError("Training Job 이름은 63자 이하여야 합니다")
    tags = [{"key": "model-id", "value": model_id},
            {"key": "model-version", "value": f"V{version}"}]
    return name, version, tags
TRAINING_IMAGE = (
    "366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/"
    "sagemaker-scikit-learn:1.9-0"
)


def _s3_uri(value: str) -> str:
    """AWS 조회 없이 일반 S3 버킷 URI 형식만 확인한다."""
    parsed = urlsplit(value)
    bucket = parsed.netloc
    if (
        parsed.scheme != "s3"
        or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
        or ".." in bucket or ".-" in bucket or "-." in bucket
        or re.fullmatch(r"\d+\.\d+\.\d+\.\d+", bucket)
        or parsed.query or parsed.fragment
        or any(character.isspace() for character in value)
    ):
        raise argparse.ArgumentTypeError("일반 버킷의 s3://bucket/path 형식이 필요합니다")
    return value


def _role_arn(value: str) -> str:
    """실행 Role ARN의 형식만 검증하며 존재·권한은 조회하지 않는다."""
    if not re.fullmatch(
        r"arn:aws:iam::\d{12}:role/(?:[A-Za-z0-9_+=,.@-]+/)*[A-Za-z0-9_+=,.@-]{1,64}", value
    ):
        raise argparse.ArgumentTypeError("유효한 IAM Role ARN이 필요합니다")
    return value


def main(argv=None):
    """모델 하나의 설정을 검토하고 --submit일 때만 train()을 호출한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True, choices=MODEL_IDS)
    parser.add_argument("--input-s3-uri", required=True, type=_s3_uri)
    parser.add_argument("--output-s3-uri", required=True, type=_s3_uri)
    parser.add_argument("--role-arn", required=True, type=_role_arn)
    parser.add_argument("--max-run", type=int, default=DEFAULT_MAX_RUN)
    parser.add_argument("--instance-type", default=INSTANCE_TYPE)
    parser.add_argument("--experiment-id", choices=("S1-C-V1.1-W5", "N1-C-V1.1-D4"))
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args(argv)
    experiment_models = {"S1-C-V1.1-W5": "S1-C", "N1-C-V1.1-D4": "N1-C"}
    if args.experiment_id and args.model_id != experiment_models[args.experiment_id]:
        parser.error("실험 ID와 모델이 일치해야 합니다")
    if args.max_run <= 0:
        parser.error("--max-run은 양의 정수(초)여야 합니다")

    source_dir = Path(__file__).resolve().parent
    requirements_file = "requirements-s1c-w5.txt" if args.experiment_id else "requirements.txt"
    for name in ("train_entrypoint.py", requirements_file):
        if not (source_dir / name).is_file():
            parser.error(f"필수 로컬 파일이 없습니다: {source_dir / name}")
    input_uri = args.input_s3_uri.rstrip("/")
    output_uri = args.output_s3_uri.rstrip("/")
    if (
        input_uri == output_uri
        or output_uri.startswith(input_uri + "/")
        or input_uri.startswith(output_uri + "/")
    ):
        parser.error("입력과 출력은 서로 포함되지 않는 별도 S3 경로로 지정하세요")

    job_name, model_version, tags = _job_identity(
        args.model_id, model_version="1.1" if args.experiment_id else None
    )
    hyperparameters = {"model-id": args.model_id, "model-version": model_version}
    if args.experiment_id:
        hyperparameters["experiment-id"] = args.experiment_id
        tags.append({"key": "experiment-id", "value": args.experiment_id})
        tags.extend([
            {"key": "data-version", "value": "feature-v1-label-v1-quality-v2"},
            {"key": "owner-team", "value": "E"},
        ])
    # 기본 모드는 표준 라이브러리만 사용한다. SDK import·Session도 생성하지 않는다.
    settings = {
        "mode": "submit" if args.submit else "review_only",
        "model_id": args.model_id,
        "model_version": f"V{model_version}",
        "experiment_id": args.experiment_id,
        "changed_only": ({"max_depth": 4} if args.experiment_id == "N1-C-V1.1-D4"
                         else {"scale_pos_weight": 5.0} if args.experiment_id else {}),
        "hyperparameters": hyperparameters,
        "required_xgboost_version": "3.4.1" if args.experiment_id else None,
        "training_job_name_example": job_name,
        "job_name_note": "실제 timestamp는 SDK가 제출 시 생성합니다 (UTC)",
        "tags": tags,
        "region": REGION,
        "training_image": TRAINING_IMAGE,
        "instance_type": args.instance_type,
        "instance_count": INSTANCE_COUNT,
        "max_runtime_in_seconds": args.max_run,
        "source_dir": str(source_dir),
        "entry_script": "train_entrypoint.py",
        "requirements": requirements_file,
        "input_s3_uri": args.input_s3_uri,
        "output_s3_uri": args.output_s3_uri,
        "role_arn": args.role_arn,
        "channel_name": "train",
        "spot_training": False,
        "automatic_job_retry": False,
    }
    print(json.dumps(settings, ensure_ascii=False, indent=2))
    if not args.submit:
        return settings

    # 실제 SDK 초기화·인증·소스 업로드·Job 제출은 승인된 분기에서만 가능하다.
    import boto3
    from importlib.metadata import version

    if version("sagemaker").split(".")[0] != "3":
        raise RuntimeError("제출 환경에는 SageMaker Python SDK 3.x가 필요합니다")
    from sagemaker.train import ModelTrainer
    from sagemaker.core.helper.session_helper import Session
    from sagemaker.core.training.configs import (
        Compute,
        InputData,
        OutputDataConfig,
        SourceCode,
    )
    from sagemaker.core.shapes import StoppingCondition

    output = urlsplit(args.output_s3_uri)
    session = Session(
        boto_session=boto3.Session(region_name=REGION),
        default_bucket=output.netloc,
        default_bucket_prefix=output.path.strip("/") or None,
    )
    trainer = ModelTrainer(
        training_image=TRAINING_IMAGE,
        role=args.role_arn,
        sagemaker_session=session,
        source_code=SourceCode(
            source_dir=str(source_dir),
            entry_script="train_entrypoint.py",
            requirements=requirements_file,
        ),
        compute=Compute(
            instance_type=args.instance_type,
            instance_count=INSTANCE_COUNT,
            enable_managed_spot_training=False,
        ),
        stopping_condition=StoppingCondition(max_runtime_in_seconds=args.max_run),
        output_data_config=OutputDataConfig(s3_output_path=args.output_s3_uri),
        hyperparameters=hyperparameters,
        tags=tags,
        base_job_name=f"e-ml-{args.model_id.lower()}-v{model_version.replace('.', '-')}",
    )
    # 전체 입력을 train 채널에 전달한다. 물질 선필터링·여러 Job 반복 제출은 없다.
    return trainer.train(
        input_data_config=[InputData(channel_name="train", data_source=args.input_s3_uri)],
        wait=False,
    )


if __name__ == "__main__":
    main()
