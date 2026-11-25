"""V2 부분 이력 후보 단독 제출. 기본 review_only는 AWS 호출이 없다."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sagemaker_job import (_s3_uri, _role_arn, REGION, TRAINING_IMAGE, INSTANCE_TYPE,
                           INSTANCE_COUNT)
SCALES = {"N3.1-C": 1}
DEFAULT_MAX_RUN = 10800

DEFAULT_OUTPUT_S3_URI = "s3://sagemaker-ap-northeast-2-952900391026/e-ml-training-3/N3.1-C/"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-id", choices=tuple(SCALES), required=True)
    p.add_argument("--input-s3-uri", type=_s3_uri, required=True)
    p.add_argument("--output-s3-uri", type=_s3_uri, default=DEFAULT_OUTPUT_S3_URI)
    p.add_argument("--baseline-s3-uri", type=_s3_uri, required=True, help="신뢰하는 N3-C의 model.joblib 및 metadata.json만 포함한 prefix")
    p.add_argument("--role-arn", type=_role_arn, required=True)
    p.add_argument("--instance-type", default=INSTANCE_TYPE)
    p.add_argument("--max-run", type=int, default=DEFAULT_MAX_RUN)
    p.add_argument("--confirm-normalized-silver", choices=("true", "false"), default="false")
    p.add_argument("--submit", action="store_true")
    args = p.parse_args(argv)
    output = urlsplit(args.output_s3_uri)
    input_uri = urlsplit(args.input_s3_uri)
    prefix = output.path.strip("/")
    if output.netloc != "sagemaker-ap-northeast-2-952900391026" or not (
        prefix == "e-ml-training-3/N3.1-C" or prefix.startswith("e-ml-training-3/N3.1-C/")
    ):
        p.error("출력은 s3://sagemaker-ap-northeast-2-952900391026/e-ml-training-3/N3.1-C/ 하위만 허용합니다")
    if output.netloc == input_uri.netloc and (
        output.path.rstrip("/").startswith(input_uri.path.rstrip("/") + "/")
        or input_uri.path.rstrip("/").startswith(output.path.rstrip("/") + "/")
        or input_uri.path.rstrip("/") == output.path.rstrip("/")):
        p.error("입력/출력 prefix가 겹칩니다")
    if args.max_run <= 0:
        p.error("--max-run은 양수")
    source = Path(__file__).resolve().parents[1]
    token = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    run_output = args.output_s3_uri.rstrip("/") + "/" + token
    base = f"e-ml-n3-1-c-aux-{token}"
    baseline_uri = urlsplit(args.baseline_s3_uri)
    for other in (input_uri, baseline_uri):
        if output.netloc == other.netloc and (output.path.rstrip("/") == other.path.rstrip("/")
            or output.path.rstrip("/").startswith(other.path.rstrip("/") + "/")
            or other.path.rstrip("/").startswith(output.path.rstrip("/") + "/")):
            p.error("결과 경로와 입력/기준 모델 경로가 겹칩니다")
    settings = dict(baseline_s3_uri=args.baseline_s3_uri, mode="submit" if args.submit else "review_only", model_id=args.model_id,
                    scale_pos_weight=SCALES[args.model_id], source_dir=str(source),
                    entry_script="n31/train_entrypoint.py", training_image=TRAINING_IMAGE,
                    requirements="requirements.txt", region=REGION,
                    instance_type=args.instance_type, instance_count=INSTANCE_COUNT,
                    max_run=args.max_run, input_s3_uri=args.input_s3_uri,
                    output_s3_uri=run_output, role_arn=args.role_arn, job_name=base,
                    normalized_silver_confirmed=args.confirm_normalized_silver == "true",
                    domestic_final_data_access=False,
                    container_artifact_directory=f"/opt/ml/model/{args.model_id}")
    print(json.dumps(settings, ensure_ascii=False, indent=2))
    if not args.submit:
        return settings
    if args.confirm_normalized_silver != "true":
        raise ValueError("Silver 정규화 출처 확인 전 제출할 수 없습니다")
    import boto3
    from importlib.metadata import version
    if version("sagemaker").split(".")[0] != "3":
        raise RuntimeError("SageMaker SDK 3.x 필요")
    from sagemaker.train import ModelTrainer
    from sagemaker.core.helper.session_helper import Session
    from sagemaker.core.training.configs import Compute, InputData, OutputDataConfig, SourceCode
    from sagemaker.core.shapes import StoppingCondition
    session = Session(boto_session=boto3.Session(region_name=REGION),
                      default_bucket=output.netloc, default_bucket_prefix=output.path.strip("/"))
    trainer = ModelTrainer(
        training_image=TRAINING_IMAGE, role=args.role_arn, sagemaker_session=session,
        source_code=SourceCode(source_dir=str(source), entry_script="n31/train_entrypoint.py",
                               requirements="requirements.txt"),
        compute=Compute(instance_type=args.instance_type, instance_count=INSTANCE_COUNT,
                        enable_managed_spot_training=False),
        stopping_condition=StoppingCondition(max_runtime_in_seconds=args.max_run),
        output_data_config=OutputDataConfig(s3_output_path=run_output),
        hyperparameters={"model-id": args.model_id,
                         "confirm-normalized-silver": args.confirm_normalized_silver},
        environment={"AWS_DEFAULT_REGION": REGION, "AWS_REGION": REGION},
        tags=[{"key": "experiment", "value": "a-type-auxiliary-n31"},
              {"key": "model_id", "value": args.model_id}],
        base_job_name=base,
    )
    return trainer.train(input_data_config=[
        InputData(channel_name="train", data_source=args.input_s3_uri),
        InputData(channel_name="baseline", data_source=args.baseline_s3_uri)], wait=False)


if __name__ == "__main__":
    main()
