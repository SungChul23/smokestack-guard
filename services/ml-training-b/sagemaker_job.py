"""B 단일 분류 실험 제출 설정. 기본 review_only는 AWS·SDK를 호출하지 않는다."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

if __package__:
    from .config import CEMS_INPUT_URI, CLASSIFICATION_MODELS, SOURCE_WEIGHTS, SOURCES
else:
    from config import CEMS_INPUT_URI, CLASSIFICATION_MODELS, SOURCE_WEIGHTS, SOURCES

# A 제출 코드의 인프라·SDK 3.x 구조를 계승하며 A 파일은 변경하지 않는다.
REGION = "ap-northeast-2"
INSTANCE_TYPE = "ml.m5.xlarge"
INSTANCE_COUNT = 1
DEFAULT_MAX_RUN = 3600
TRAINING_IMAGE = (
    "366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/"
    "sagemaker-scikit-learn:1.9-0"
)
B_NAMESPACE = "e-ml-training-b"


def _s3_uri(value):
    """일반 버킷 URI 검증. 대만 읽기 입력은 A 경로를 재사용한다."""
    parsed = urlsplit(value)
    bucket = parsed.netloc
    if (parsed.scheme != "s3"
        or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
        or ".." in bucket or ".-" in bucket or "-." in bucket
        or re.fullmatch(r"\d+\.\d+\.\d+\.\d+", bucket)
        or parsed.query or parsed.fragment or any(c.isspace() for c in value)):
        raise argparse.ArgumentTypeError("일반 버킷의 s3://bucket/path 형식이 필요합니다")
    parts = parsed.path.strip("/").split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise argparse.ArgumentTypeError("빈 경로·상대 경로 요소를 사용할 수 없습니다")
    return value.rstrip("/")


def _output_s3_uri(value):
    """결과·소스 업로드는 B 전용 prefix에만 허용한다."""
    value = _s3_uri(value)
    if urlsplit(value).path.strip("/").split("/")[0] != B_NAMESPACE:
        raise argparse.ArgumentTypeError(f"출력은 {B_NAMESPACE}/ 하위여야 합니다")
    return value

def _role_arn(value):
    if not re.fullmatch(
        r"arn:aws:iam::\d{12}:role/(?:[A-Za-z0-9_+=,.@-]+/)*[A-Za-z0-9_+=,.@-]{1,64}", value
    ):
        raise argparse.ArgumentTypeError("유효한 IAM Role ARN이 필요합니다")
    return value


def _job_identity(model_id, experiment):
    """SDK가 시각을 추가하는 이름 prefix와 출력 분리용 고유 실행 ID."""
    token = uuid4().hex[:12]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + "-" + token
    base = f"e-ml-b-{model_id.lower()}-w{experiment.lower()}-v2-0-{token}"
    return base, run_id


def _dependency_blockers(source, requirements):
    """B 의존성 파일을 확인만 한다. 버전을 선택하거나 설치하지 않는다."""
    path = source / requirements
    if not path.is_file():
        return [f"B 의존성 파일 없음: {requirements}; A W10/W5 고정 환경 + awswrangler 버전 확정 필요"]
    lines = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")}
    baseline = source.parent / "ml-training" / "requirements-s1c-w5.txt"
    blockers = []
    if not baseline.is_file():
        blockers.append("A W10/W5 고정 의존성 기준 파일을 확인할 수 없습니다")
    else:
        required = {line.strip() for line in baseline.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")}
        missing = sorted(required - lines)
        if missing:
            blockers.append(f"A W10/W5 고정 의존성 누락·변경: {missing}")
    if "awswrangler==3.18.0" not in lines:
        blockers.append("확인된 의존성 범위의 awswrangler==3.18.0이 필요합니다")
    return blockers


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True, choices=tuple(CLASSIFICATION_MODELS))
    parser.add_argument("--weight-experiment", required=True, choices=tuple(SOURCE_WEIGHTS))
    parser.add_argument("--input-s3-uri", default=CEMS_INPUT_URI, type=_s3_uri)
    parser.add_argument("--output-s3-uri", required=True, type=_output_s3_uri)
    parser.add_argument("--role-arn", required=True, type=_role_arn)
    parser.add_argument("--instance-type", default=INSTANCE_TYPE)
    parser.add_argument("--max-run", type=int, default=DEFAULT_MAX_RUN)
    parser.add_argument("--requirements-file", default="requirements.txt")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args(argv)
    if args.max_run <= 0:
        parser.error("--max-run은 양의 정수여야 합니다")
    if Path(args.requirements_file).name != args.requirements_file or "/" in args.requirements_file or "\\" in args.requirements_file:
        parser.error("--requirements-file은 B 디렉터리 내부의 파일명이어야 합니다")
    input_uri, output_uri = args.input_s3_uri, args.output_s3_uri
    if (input_uri == output_uri or output_uri.startswith(input_uri + "/")
        or input_uri.startswith(output_uri + "/")):
        parser.error("입력·출력 S3 prefix는 서로 포함되지 않아야 합니다")
    source = Path(__file__).resolve().parent
    for name in ("train_entrypoint.py", "train_classifier.py", "mixed_dataset.py",
                 "config.py", "contract.py", "dataset.py", "split.py", "evaluation.py",
                 "artifacts.py", "monitoring.py"):
        if not (source / name).is_file():
            parser.error(f"B 소스 파일이 없습니다: {name}")
    base, run_id = _job_identity(args.model_id, args.weight_experiment)
    run_output = f"{output_uri}/{args.model_id}/weights-{args.weight_experiment}/{run_id}"
    blockers = _dependency_blockers(source, args.requirements_file)
    hyperparameters = {"model-id": args.model_id, "weight-experiment": args.weight_experiment}
    tags = [{"key": "scenario", "value": "B"}, {"key": "model-id", "value": args.model_id},
            {"key": "model-version", "value": "V2"},
            {"key": "weight-experiment", "value": args.weight_experiment}]
    settings = {
        "mode": "submit" if args.submit else "review_only", "blockers": blockers,
        "model_id": args.model_id, "weight_experiment": args.weight_experiment,
        "scale_pos_weight": CLASSIFICATION_MODELS[args.model_id]["scale_pos_weight"],
        "source_weights": SOURCE_WEIGHTS[args.weight_experiment],
        "region": REGION, "instance_type": args.instance_type, "instance_count": INSTANCE_COUNT,
        "max_runtime_in_seconds": args.max_run, "training_image": TRAINING_IMAGE,
        "source_dir": str(source), "entry_script": "train_entrypoint.py",
        "requirements": args.requirements_file, "job_name_prefix": base, "run_id": run_id,
        "input_s3_uri": input_uri, "output_s3_uri": run_output, "channel_name": "train",
        "hyperparameters": hyperparameters, "tags": tags,
        "domestic_inputs": {
            name: {"table": item.table, "snapshot_id": item.snapshot_id,
                   "access": "Athena FOR VERSION AS OF; ctas_approach=False"}
            for name, item in SOURCES.items() if name != "tw_cems"
        },
        "container_artifact_directory": f"/opt/ml/model/weights-{args.weight_experiment}/{args.model_id}",
        "spot_training": False, "automatic_job_retry": False,
    }
    print(json.dumps(settings, ensure_ascii=False, indent=2))
    if not args.submit:
        return settings
    if blockers:
        raise RuntimeError("제출 차단: " + "; ".join(blockers))

    # AWS 초기화·업로드·Job 제출은 명시적 승인 후 --submit에서만 수행한다.
    import boto3
    from importlib.metadata import version
    if version("sagemaker").split(".")[0] != "3":
        raise RuntimeError("SageMaker SDK 3.x가 필요합니다")
    from sagemaker.train import ModelTrainer
    from sagemaker.core.helper.session_helper import Session
    from sagemaker.core.training.configs import Compute, InputData, OutputDataConfig, SourceCode
    from sagemaker.core.shapes import StoppingCondition

    output = urlsplit(run_output)
    session = Session(boto_session=boto3.Session(region_name=REGION),
                      default_bucket=output.netloc, default_bucket_prefix=output.path.strip("/"))
    trainer = ModelTrainer(
        training_image=TRAINING_IMAGE,
        role=args.role_arn,
        sagemaker_session=session,
        environment={
            "AWS_DEFAULT_REGION": REGION,
            "AWS_REGION": REGION,
        },
        source_code=SourceCode(source_dir=str(source), entry_script="train_entrypoint.py",
                               requirements=args.requirements_file),
        compute=Compute(instance_type=args.instance_type, instance_count=INSTANCE_COUNT,
                        enable_managed_spot_training=False),
        stopping_condition=StoppingCondition(max_runtime_in_seconds=args.max_run),
        output_data_config=OutputDataConfig(s3_output_path=run_output),
        hyperparameters=hyperparameters, tags=tags, base_job_name=base,
    )
    return trainer.train(
        input_data_config=[InputData(channel_name="train", data_source=input_uri)], wait=False
    )


if __name__ == "__main__":
    main()
