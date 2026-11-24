"""S3.1-C 전용 확정 설정. 기존 N3-C/S3-C 설정을 바꾸지 않는다."""
from config import CEMS_INPUT_URI, FEATURE_COLUMNS

MODEL_ID = "S3.1-C"
POLLUTANT = "sox"
SCALE_POS_WEIGHT = 5
REGION = "ap-northeast-2"
DATABASE = "tms_silver2"
WORKGROUP = "tms-eda"
DOMESTIC_START = "2026-10-31 00:00:00"
DOMESTIC_END_EXCLUSIVE = "2026-11-11 00:00:00"
DOMESTIC_USABLE_END_EXCLUSIVE = "2026-11-10 23:00:00"
# 첫 Train 행의 기준치 변경·과거 관측 검증에만 사용. 이 구간은 학습에 넣지 않는다.
CONTEXT_START = "2026-10-30 21:30:00"
SNAPSHOTS = {
    "ktms": {"table": "ktms_ml_ready", "snapshot_id": 5489130650729135006},
    "ktms_synth": {"table": "ktms_synth_ml_ready", "snapshot_id": 7512479067515746500},
}
OUTPUT_S3_ROOT = "s3://sagemaker-ap-northeast-2-952900391026/e-ml-training-3/S3.1-C/"
