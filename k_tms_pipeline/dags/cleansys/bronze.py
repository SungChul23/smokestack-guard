import gzip
import json
import os

from datetime import datetime, timezone
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from .client import FetchResult, inspect_payload

BUCKET = os.environ.get("BRONZE_BUCKET", "bronze")  # BUCKET 이름 설정
PREFIX = "tms_cleansys"                                  # S3 저장 경로 Prefix
CONN_ID = "aws_default"                                  # Airflow Connection ID 

# AWS 연걸 ID를 사용해 S3 접근용 Hook 생성
def _hook():
    return S3Hook(aws_conn_id = CONN_ID)

# 버킷 생성 확인
def ensure_bucket():
    hook = _hook()
    if not hook.check_for_bucket(BUCKET):           # 버킷 존재 확인
        hook.create_bucket(bucket_name = BUCKET)    # 없다면 새로 생성

# S3 지정 경로에 데이터 저장
def put_object(key, data):
    _hook().load_bytes(data, key = key, bucket_name = BUCKET, replace = True) 

# 실행 시간을 기준으로 S3 저장 경로를 생성
def build_prefix(run_ts: datetime) -> str:         
    t = run_ts.astimezone(timezone.utc)  # 입력받은 시각을 UTC 기준으로 변환
    # 날짜별, 시간별, 실행시각별 파티션 경로 문자열 생성, 반환
    return f"{PREFIX}/ingest_date={t:%Y-%m-%d}/hour={t:%H}/run_ts={t:%Y%m%dT%H%M%SZ}" 

# 수집 수행 이력, 데이터 크기, 검증 결과 등 메타데이터 dict 생성
def build_meta(result: FetchResult, run_ts: datetime, raw_key: str, gz_size: int, inspected: dict) -> dict:
    return {
        "source": "data.go.kr/B552584/cleansys/rltmMesureResult",
        "run_ts": run_ts.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "requested_at": result.requested_at,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status_code": result.status_code,
        "elapsed_ms": result.elapsed_ms,
        "attempts": result.attempts,
        "raw_bytes": len(result.content),
        "gz_bytes": gz_size,
        "sha256_raw": result.sha256,
        "raw_key": raw_key,
        "inspect": inspected,
    }

# 수집 결과와 실행 시각을 받아 S3에 저장, 결과 반환
def save_snapshot(result: FetchResult, run_ts: datetime) -> dict:
    ensure_bucket()                                         # 저장할 버킷이 존재하지 않는다면 생성
    prefix = build_prefix(run_ts)                      # 실행 시각 기준 Prefix 생성
    raw_key = f"{prefix}/snapshot.json.gz"             # 원본 데이터 저장 경로 정의
    meta_key = f"{prefix}/snapshot.meta.json"          # 메타 데이터 저장 경로 정의

    gz = gzip.compress(result.content, mtime = 0)    # 원본 데이터를 gzip 형식으로 압축
    put_object(raw_key, gz)                                 # 압축된 원본 데이터 업로드

    inspected = inspect_payload(result.content)                                         # 원본 데이터 내용 검증(구조, 개수 확인)
    meta = build_meta(result, run_ts, raw_key, len(gz), inspected)                      # 메타데이터 dict 생성
    put_object(meta_key, json.dumps(meta, ensure_ascii = False, indent = 2).encode("utf-8"))  # 메타데이터를 JSON 형식으로 변환 후 업로드

    return {"raw_key": raw_key, "meta_key": meta_key, "inspect": inspected}                   # 최종 저장 경로, 검증 결과 dict 형식으로 반환