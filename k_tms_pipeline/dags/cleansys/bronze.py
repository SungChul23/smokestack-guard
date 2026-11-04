import gzip
import json
import os
import hashlib
import shutil

from datetime import datetime, timezone
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from .client import FetchResult, inspect_payload

BUCKET = os.environ.get("BRONZE_BUCKET", "bronze")  # BUCKET 이름 설정
PREFIX = "tms_cleansys"                                  # S3 저장 경로 Prefix
CONN_ID = "aws_default"                                  # Airflow Connection ID 

BUFFER_DIR = os.environ.get("BRONZE_BUFFER_DIR", "/opt/airflow/buffer")     # 업로드 전 임시 보관 폴더
RAW_NAME = "snapshot.json.gz"                                                    # 원본 파일명
META_NAME = "snapshot.meta.json"                                                 # 메타 파일명
MANIFEST_NAME = "manifest.json"                                                  # 파일 목록, 해시 기록
SUCCESS_NAME = "_SUCCESS"                                                        # 확정 표지

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

# 도구
## Byte 데이터의 SHA256 해시 계산
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

## 실행 시각별 버퍼 폴더 경로
def buffer_dir_for(run_ts: datetime) -> str:
    t = run_ts.astimezone(timezone.utc)
    return os.path.join(BUFFER_DIR, f"{t:%Y%m%dT%H%M%SZ}")

## local 파일 쓰기, 읽기
def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)

def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

# 버퍼에 저장
## 응답 압축 및 메타데이터와 함께 버퍼에 저장
def stage_snapshot(result: FetchResult, run_ts: datetime) -> dict:
    prefix = build_prefix(run_ts)                                                   
    gz = gzip.compress(result.content, mtime = 0)                                   # 원본 압축
    inspected = inspect_payload(result.content)                                      # 응답 점검 결과
    meta = build_meta(result, run_ts, f"{prefix}/{RAW_NAME}", len(gz), inspected)    # 메타 데이터 생성

    folder = buffer_dir_for(run_ts)                                                   # 실행시각 기준 임시 저장 로컬 폴더 생성
    os.makedirs(folder, exist_ok = True)                                                   # 해당 폴더가 없다면 새로 생성
    _write(os.path.join(folder, RAW_NAME), gz)                                             # 압축된 실제 데이터를 로컬 버퍼 폴더 안에 작성
    _write(os.path.join(folder, META_NAME), json.dumps(meta, ensure_ascii = False, indent = 2).encode("utf-8")) # meta 데이터를 json 문자열로 변형, 인코딩 후 로컬 버퍼에 작성
    return {"buffer_dir": folder}                                                          # 작업 성공시 로컬 버퍼 폴더 경로 dict 형태로 반환

# 업로드, 검증
## 버퍼 파일 s3로 업로드, 해시값 검증
def upload_and_verify(run_ts: datetime) -> dict:
    ensure_bucket()                                                                         # 버킷 확인, 준비, 생성
    prefix = build_prefix(run_ts)                                                      # 실행시간 기반 파일 저장 경로 생성
    folder = buffer_dir_for(run_ts)                                                    # 실행시간에 해당하는 임시 버퍼 디렉토리 경로
    gz = _read(os.path.join(folder, RAW_NAME))                                       # 버퍼 디렉토리에 존재하는 압축 원본 파일을 읽어와 저장
    meta_bytes = _read(os.path.join(folder, META_NAME))                              # 버퍼 디렉토리에 존재하는 메타데이터 파일을 읽어와 저장
    meta = json.loads(meta_bytes)                                                      # 메타데이터를 JSON 형태로 파싱

    if sha256_hex(gzip.decompress(gz)) != meta["sha256_raw"]:                               # 읽어온 압축 파일을 해제한 데이터의 해시값과 메타데이터에 기록된 해시값 비교
        raise ValueError("버퍼 파일이 원문과 다름")                                          # 해시값이 일치하지 않으면 예외처리

    files = []                                                                        # 업로드 결과 정보 저장 리스트
    for name, data in ((RAW_NAME, gz), (META_NAME, meta_bytes)):                            # 압축된 원본 파일과 메타데이터 파일을 순회하며 업로드, 검증 진행
        key = f"{prefix}/{name}"                                                       # 저장될 최종 객체 키 생성
        put_object(key, data)                                                               # 데이터를 해당 키 경로로 원격 저장소에 업로드
        stored = _hook().get_key(key, BUCKET).get()["Body"].read()                     # 업로드된 객체를 다시 읽어와 본문 데이터를 가져옴(binary)

        if sha256_hex(stored) != sha256_hex(data):                                          # 저장소에서 읽어온 데이터의 해시값과 업로드 전 데이터의 해시값 비교
            raise ValueError(f"업로드 검증 실패: {key}")                                     # 해시값이 다르다면 데이터 손상으로 판단 후 예외 처리
        files.append({"name": name, "bytes": len(data), "sha256": sha256_hex(data)})        # 검증 완료된 파일 정보를 결과 리스트에 추가 

    shutil.rmtree(folder)                                                                   # 임시 버퍼 디렉토리 삭제
    return {"files": files, "raw_sha256": meta["sha256_raw"], "inspect": meta["inspect"]}   # 최종 파일정보 목록, 원본 해시값, 검증 관련 메타데이터 dict로 반환

# 확정짓기
## 응답 점검 통과시 manifest, _SUCCESS 기록, 불통과시 False
def commit_snapshot(run_ts: datetime, verified: dict) -> bool:
    if not verified["inspect"]["ok"]:                                                                                  # 메타데이터에서 검증 상태가 ok 인지 확인
        return False                                                                                                   # ok 상태가 아니라면 manifest 생성 중단 및 실패 반환

    prefix = build_prefix(run_ts)                                                                                 # 실행 시간 기반 저장소 경로 생성
    manifest = {                                                                                       # manifest dict 구성
        "manifest_version": 1,                                                                                         # manifest 버전
        "files": verified["files"],                                                                                    # 검증 완료된 파일 상세 목록
        "ras_sha256": verified["raw_sha256"],                                                                          # 원본 데이터 해시값
        "committed_at": datetime.now(timezone.utc).isoformat(timespec = "seconds"),                                    # 현재 시각
    }
    put_object(f"{prefix}/{MANIFEST_NAME}", json.dumps(manifest, ensure_ascii = False, indent = 2).encode("utf-8"))    # menifest를 json 형태로 저장
    put_object(f"{prefix}/{SUCCESS_NAME}", b"")                                                                        # 데이터 정상 수집 완료 마커 파일 _SUCCESS 파일 생성
    return True