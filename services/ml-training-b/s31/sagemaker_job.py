"""S3.1-C 전용 제출 준비. 기본 실행은 AWS 비호출 review_only."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sagemaker_job import (
    _s3_uri, _role_arn, REGION, TRAINING_IMAGE, INSTANCE_TYPE, INSTANCE_COUNT, DEFAULT_MAX_RUN)
from s31.config import MODEL_ID, SCALE_POS_WEIGHT, OUTPUT_S3_ROOT, CEMS_INPUT_URI, SNAPSHOTS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", choices=(MODEL_ID,), default=MODEL_ID)
    parser.add_argument("--input-s3-uri", type=_s3_uri, default=CEMS_INPUT_URI)
    parser.add_argument("--output-s3-uri", type=_s3_uri, default=OUTPUT_S3_ROOT)
    parser.add_argument("--role-arn", type=_role_arn, required=True)
    parser.add_argument("--instance-type", default=INSTANCE_TYPE)
    parser.add_argument("--max-run", type=int, default=DEFAULT_MAX_RUN)
    parser.add_argument("--confirm-normalized-silver", choices=("true", "false"), default="false")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args(argv)
    if args.output_s3_uri.rstrip("/") != OUTPUT_S3_ROOT.rstrip("/"):
        parser.error("출력은 " + OUTPUT_S3_ROOT + " 만 허용합니다. 모델 폴더를 다시 붙이지 마세요")
    if args.max_run <= 0:
        parser.error("--max-run은 양수여야 합니다")
    source = Path(__file__).resolve().parents[1]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    # S3.1-C는 S3 prefix/metadata에서 유지하고 Job 이름에서만 점을 하이픈으로 바꾼다.
    job = "e-ml-s3-1-c-mixed-" + run_id
    output = OUTPUT_S3_ROOT.rstrip("/") + "/" + run_id
    settings = dict(
        mode="submit" if args.submit else "review_only", model_id=MODEL_ID,
        scale_pos_weight=SCALE_POS_WEIGHT, fit_uses_sample_weight=False,
        snapshots=SNAPSHOTS, input_s3_uri=args.input_s3_uri, output_s3_uri=output,
        job_name=job, source_dir=str(source), entry_script="s31/train_entrypoint.py",
        requirements="requirements.txt", training_image=TRAINING_IMAGE, region=REGION,
        instance_type=args.instance_type, instance_count=INSTANCE_COUNT, max_run=args.max_run,
        container_artifacts="/opt/ml/model/S3.1-C/{model.joblib,metrics.json,metadata.json}",
        domestic_train="2026-10-31..2026-11-10; last 60min embargo",
        domestic_query_context="2026-10-30 21:30 onward; never training rows",
        domestic_evaluation_access=False,
    )
    print(json.dumps(settings, ensure_ascii=False, indent=2))
    if not args.submit:
        return settings
    if args.confirm_normalized_silver != "true":
        raise ValueError("세 출처의 Silver 정규화 계약 확인이 필요합니다")
    import boto3
    from importlib.metadata import version
    if version("sagemaker").split(".")[0] != "3":
        raise RuntimeError("기존 제출용 SageMaker SDK 3.x 환경이 필요합니다")
    from sagemaker.train import ModelTrainer
    from sagemaker.core.helper.session_helper import Session
    from sagemaker.core.training.configs import Compute, InputData, OutputDataConfig, SourceCode
    from sagemaker.core.shapes import StoppingCondition
    session = Session(
        boto_session=boto3.Session(region_name=REGION),
        default_bucket="sagemaker-ap-northeast-2-952900391026",
        default_bucket_prefix="e-ml-training-3/S3.1-C",
    )
    trainer = ModelTrainer(
        training_image=TRAINING_IMAGE, role=args.role_arn, sagemaker_session=session,
        source_code=SourceCode(source_dir=str(source), entry_script="s31/train_entrypoint.py",
                               requirements="requirements.txt"),
        compute=Compute(instance_type=args.instance_type, instance_count=INSTANCE_COUNT,
                        enable_managed_spot_training=False),
        stopping_condition=StoppingCondition(max_runtime_in_seconds=args.max_run),
        output_data_config=OutputDataConfig(s3_output_path=output),
        hyperparameters={"model-id": MODEL_ID,
                         "confirm-normalized-silver": args.confirm_normalized_silver},
        environment={"AWS_DEFAULT_REGION": REGION, "AWS_REGION": REGION},
        tags=[{"key": "model_id", "value": MODEL_ID}, {"key": "experiment", "value": "mixed-partial-history"}],
        base_job_name=job,
    )
    return trainer.train(input_data_config=[
        InputData(channel_name="train", data_source=args.input_s3_uri)], wait=False)


if __name__ == "__main__":
    main()
