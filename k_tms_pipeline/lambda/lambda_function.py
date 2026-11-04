import gzip
import hashlib
import http.client
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError, BotoCoreError

URL = "https://apis.data.go.kr/B552584/cleansys/rltmMesureResult"
RETRY_STATUS = {429, 500, 502, 503, 504}    # 재시도 대상 HTTP 상태 코드
MAX_ATTEMPTS = 3                            # 최대 시도 횟수
BACKOFF_SECONDS = (2, 5)                    # 처음 실패시 2초, 다음 실패시 5초 대기
TIMEOUT = 60                                # 소켓 타임아웃(초)

BUCKET = os.environ["BRONZE_BUCKET"]        # 저장할 S3 버킷 이름
API_KEY_PARAMETER = os.environ["API_KEY_PARAMETER"]  # API 키가 담긴 SSM 파라미터 이름
PREFIX = "tms_cleansys"                     # S3 저장 경로 Prefix
INTERVAL_MINUTES = 10                       # 수집 주기
STATE_KEY = f"{PREFIX}/_state/latest.json"  # 마지막 수집 상태 파일 경로

BUFFER_DIR = "/tmp/bronze_buffer"           # Lambda에서 사용할 임시 디스크
RAW_NAME = "snapshot.json.gz"               # 원본 파일명
META_NAME = "snapshot.meta.json"            # 메타 파일명
MANIFEST_NAME = "manifest.json"             # 파일명, 해시 기록 파일
SUCCESS_NAME = "_SUCCESS"                   # 업로드 확정 표지
UPLOAD_ATTEMPTS = 3                          # 업로드 최대 시도 횟수
UPLOAD_BACKOFF_SECONDS = (1, 3)             # 업로드 실패 대기

s3 = boto3.client("s3")                     # 핸들러 밖에서 생성해 재사용
ssm = boto3.client("ssm")
_api_key = None                             # 실행 환경이 살아 있는 동안 재사용


# API 데이터 호출 실패를 나타내는 사용자 정의 클래스
class FetchError(Exception):
    """
        호출 실패 class
    """

# 업로드, 해시 검증 실패를 나타내는 사용자 정의 클래스
class UploadError(Exception):
    """
        업로드 실패 class
    """


# frozen = True 설정으로 데이터 수정/변경 불가
@dataclass(frozen = True)
class FetchResult:
    content: bytes      # 수집한 원본 그대로
    status_code: int    # HTTP 응답 상태 코드
    requested_at: str   # 요청 시간
    elapsed_ms: int     # 처리 시간
    attempts: int       # 시도 횟수
    sha256: str         # 데이터 무결성 검증 SHA256 해시값


# SSM에서 API 키를 읽어 전역 변수에 캐시
def get_api_key() -> str:
    global _api_key
    if _api_key is None:
        response = ssm.get_parameter(Name = API_KEY_PARAMETER, WithDecryption = True)
        _api_key = response["Parameter"]["Value"]
    return _api_key


# API Key를 이용해 Http Get 요청
def _get(api_key: str) -> tuple[int, bytes]:
    query = urllib.parse.urlencode({"serviceKey": api_key, "type": "json"})
    with urllib.request.urlopen(f"{URL}?{query}", timeout = TIMEOUT) as resp:
        return resp.status, resp.read()


# API 호출 시도 및 결과 FetchResult로 반환 (실패시 재시도)
def fetch_snapshot(api_key: str) -> FetchResult:
    requested_at = datetime.now(timezone.utc).isoformat(timespec = "seconds")
    last_error = "알 수 없음"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.perf_counter()
        try:
            status_code, content = _get(api_key)
        except urllib.error.HTTPError as exc:                       # urllib은 200 외 상태를 예외로 발생시킴
            if exc.code not in RETRY_STATUS:                        # 재시도 대상이 아니면 즉시 실패
                raise FetchError(f"HTTP {exc.code}") from None
            last_error = f"HTTP {exc.code}"
        except (OSError, http.client.HTTPException) as exc:         # 연결, 타임아웃 등 네트워크 오류
            last_error = type(exc).__name__                         # URL에 키가 있으므로 에러 유형만 기록
        else:
            return FetchResult(
                content = content,
                status_code = status_code,
                requested_at = requested_at,
                elapsed_ms = int((time.perf_counter() - start) * 1000),
                attempts = attempt,
                sha256 = hashlib.sha256(content).hexdigest()
            )
        if attempt < MAX_ATTEMPTS:                                  # 다음 재시도 전 BACKOFF 시간만큼 대기
            time.sleep(BACKOFF_SECONDS[attempt - 1])
    raise FetchError(f"{MAX_ATTEMPTS}회 모두 실패: {last_error}")


# 수집된 데이터 구조, 내용 유효성 검사
def inspect_payload(content: bytes) -> dict:
    try:
        data = json.loads(content)
        header = data["response"]["header"]
        items = data["response"]["body"]["items"]
    except (ValueError, KeyError, TypeError):
        return {"ok": False, "reason": "JSON 구조가 예상과 다름"}

    result_code = header.get("resultCode")
    total_count = header.get("totalCount")
    item_count = len(items)

    ok = result_code == "0" and total_count == item_count           # 결과 코드 = 0, 전체 건수 = 실제 건수
    return {
        "ok": ok,
        "result_code": result_code,
        "total_count": total_count,
        "item_count": item_count,
        "reason": None if ok else "resultCode 또는 건수 불일치"
    }


# 이벤트 시각을 수집 주기 단위로 내림 (재시도해도 같은 경로에 저장되도록)
def resolve_run_ts(event: dict) -> datetime:
    raw = event.get("time")                                         # 콘솔 테스트 이벤트에는 time이 없을 수 있음
    t = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else datetime.now(timezone.utc)
    return t.replace(minute = t.minute - t.minute % INTERVAL_MINUTES, second = 0, microsecond = 0)


# 실행 시간을 기준으로 S3 저장 경로를 생성
def build_prefix(run_ts: datetime) -> str:
    t = run_ts.astimezone(timezone.utc)
    return f"{PREFIX}/ingest_date={t:%Y-%m-%d}/hour={t:%H}/run_ts={t:%Y%m%dT%H%M%SZ}"


# 수집 수행 이력, 데이터 크기, 검증 결과 등 메타데이터 dict 생성
def build_meta(result: FetchResult, run_ts: datetime, raw_key: str, gz_size: int, inspected: dict) -> dict:
    return {
        "source": "data.go.kr/B552584/cleansys/rltmMesureResult",
        "run_ts": run_ts.astimezone(timezone.utc).isoformat(timespec = "seconds"),
        "requested_at": result.requested_at,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec = "seconds"),
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

# def save_snapshot(result: FetchResult, run_ts: datetime) -> dict:
#     prefix = build_prefix(run_ts)
#     raw_key = f"{prefix}/snapshot.json.gz"
#     meta_key = f"{prefix}/snapshot.meta.json"

#     gz = gzip.compress(result.content, mtime = 0)
#     s3.put_object(Bucket = BUCKET, Key = raw_key, Body = gz, ContentType = "application/gzip")

#     inspected = inspect_payload(result.content)                     # 검증 실패 원문도 남기기 위해 저장 후 검증
#     meta = build_meta(result, run_ts, raw_key, len(gz), inspected)
#     s3.put_object(
#         Bucket = BUCKET,
#         Key = meta_key,
#         Body = json.dumps(meta, ensure_ascii = False, indent = 2).encode("utf-8"),
#         ContentType = "application/json"
#     )
#     return {"raw_key": raw_key, "meta_key": meta_key, "inspect": inspected}

# 데이터의 SHA256 해시
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

# 실행 시각별 buffer 폴더 경로
def buffer_dir_for(run_ts: datetime) -> str:
    t = run_ts.astimezone(timezone.utc)
    return os.path.join(BUFFER_DIR, f"{t:%Y%m%dH%H%M%SZ}")

# local 파일 쓰기, 읽기
def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)

def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

# 응답 압축 및 메타와 함께 /tmp buffer에 저장
def stage_snapshot(result: FetchResult, run_ts: datetime) -> None:
    prefix = build_prefix(run_ts)
    gz = gzip.compress(result.content, mtime = 0)
    inspected = inspect_payload(result.content)
    meta = build_meta(result, run_ts, f"{prefix}/{RAW_NAME}", len(gz), inspected)

    folder = buffer_dir_for(run_ts)
    os.makedirs(folder, exist_ok = True)
    _write(os.path.join(folder, RAW_NAME), gz)
    _read(os.path.join(folder, META_NAME), json.dumps(meta, ensure_ascii = False, indent = 2).encode("utf-8"))

# 파일을 읽어 해시 비교
def put_and_verify(key: str, data: bytes, content_type: str) -> None:
    last_error = "알 수 없음"
    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        try:
            stored = s3.put.object(Bucket = BUCKET, Key = key)["Body"].read()
            if sha256_hex(stored) == sha256_hex(data):
                return
            last_error = "해시 불일치"
        except ClientError as exc:
            last_error = exc.response["Error"]["Code"]
        except BotoCoreError as exc:
            last_error = type(exc).__name__
        if attempt < UPLOAD_ATTEMPTS:
            time.sleep(UPLOAD_BACKOFF_SECONDS[attempt - 1])
    raise UploadError(f"{key} 업로드 {UPLOAD_ATTEMPTS}회 실패: {last_error}")

# 버퍼의 파일을 S3로 올리고 검증 결과 반환
def upload_and_verify(run_ts: datetime) -> dict:
    prefix = build_prefix(run_ts)
    folder = buffer_dir_for(run_ts)
    gz = _read(os.path.join(folder, RAW_NAME))
    meta_bytes = _read(os.path.join(folder, META_NAME))
    meta = json.load(meta_bytes)

    if sha256_hex(gzip.decompress(gz)) != meta["sha256_raw"]:
        raise UploadError("버퍼 파일이 원문과 다름")

    files = []
    for name, data, content_type in (
        (RAW_NAME, gz, "application/gzip"),
        (META_NAME, meta_bytes, "application/json")
    ):
        put_and_verify(f"{prefix}/{name}", data, content_type)
        files.append({"name": name, "bytes": len(data), "sha256": sha256_hex(data)})

    return {
        "raw_key": f"{prefix}/{RAW_NAME}",
        "meta_key": f"{prefix}/{META_NAME}",
        "files": files,
        "raw_sha256": meta["sha256_raw"],
        "inspect": meta["inspect"],
    }

# 검증 통과시 manifest, _SUCCESS 기록
def commit_snapshot(run_ts: datetime, verified: dict) -> bool:
    if not verified["inspect"]["ok"]:
        return False

    prefix = build_prefix(run_ts)
    manifest = {
        "manifest_version": 1,
        "files": verified["files"],
        "raw_sha256": verified["raw_sha256"],
        "committed_at": datetime.now(timezone.utc).isoformat(timespec = "seconds"),
    }
    put_and_verify(
        f"{prefix}/{MANIFEST_NAME}",
        json.dumps(manifest, ensure_ascii = False, indent = 2).encode("uft-8"),
        "application/json",
    )
    put_and_verify(f"{prefix}/{SUCCESS_NAME}", b"", "application/object-stream")
    return True


# 마지막 수집 상태 조회 (첫 실행이면 None)
def load_state() -> dict | None:
    try:
        return json.loads(s3.get_object(Bucket = BUCKET, Key = STATE_KEY)["Body"].read())
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code not in ("NoSuchKey", "AccessDenied"):               # ListBucket 권한이 없으면 없는 키도 AccessDenied로 응답
            raise
        print(json.dumps({"state": "없음", "code": code}, ensure_ascii = False))
        return None                                                 # 상태를 못 읽어도 원문은 저장해 수집 공백을 막음


# 마지막 수집 상태 저장
def save_state(state: dict) -> None:
    s3.put_object(
        Bucket = BUCKET,
        Key = STATE_KEY,
        Body = json.dumps(state, ensure_ascii = False, indent = 2).encode("utf-8"),
        ContentType = "application/json"
    )


# EventBridge Scheduler가 호출하는 진입점
def lambda_handler(event, context):
    run_ts = resolve_run_ts(event)
    run_ts_iso = run_ts.isoformat(timespec = "seconds")
    result = fetch_snapshot(get_api_key())
    state = load_state()

    if state and state["sha256_raw"] == result.sha256:              # 이전 응답과 같으면 원문 저장 생략
        save_state({**state, "last_checked_at": run_ts_iso})
        print(json.dumps({
            "changed": False,
            "item_count": inspect_payload(result.content).get("item_count"),
            "raw_key": state["raw_key"],
            "last_changed_at": state["last_changed_at"],
            "attempts": result.attempts,
            "elapsed_ms": result.elapsed_ms,
        }, ensure_ascii = False))
        return {"changed": False, "last_changed_at": state["last_changed_at"]}

    # saved = save_snapshot(result, run_ts)

    # inspected = saved["inspect"]
    # if not inspected["ok"]:                                         # 예외를 던져야 Lambda 실패로 집계됨
    #     raise RuntimeError(                                         # 상태는 갱신하지 않아 마지막 정상 응답과 계속 비교
    #         f"원문 점검 실패: {inspected.get('reason')} "
    #         f"(total = {inspected.get('total_count')}, items = {inspected.get('item_count')})"
    #     )

    # save_state({                                                    # 원문, 메타 저장이 끝난 뒤 마지막에 갱신
    #     "sha256_raw": result.sha256,
    #     "last_changed_at": run_ts_iso,
    #     "last_checked_at": run_ts_iso,
    #     "raw_key": saved["raw_key"],
    # })
    # print(json.dumps({"changed": True, **saved, "attempts": result.attempts, "elapsed_ms": result.elapsed_ms}, ensure_ascii = False))
    # return {"changed": True, **saved}

    folder = buffer_dir_for(run_ts)
    try:
        stage_snapshot(result, run_ts)                              # /tmp 버퍼에 저장
        verified = upload_and_verify(run_ts)                  # S3 업로드와 해시 검증 (업로드만 재시도)
    finally:
        shutil.rmtree(folder, ignore_errors = True)                 # 성공, 실패와 관계없이 /tmp 정리

    if not commit_snapshot(run_ts, verified):                       # 예외를 던져야 Lambda 실패로 집계됨
        inspected = verified["inspect"]
        raise RuntimeError(                                         # 상태는 갱신하지 않아 마지막 정상 응답과 계속 비교
            f"원문 점검 실패: {inspected.get('reason')} "
            f"(total = {inspected.get('total_count')}, items = {inspected.get('item_count')})"
        )

    save_state({                                                    # 원문, 메타, 표지 기록이 끝난 뒤 마지막에 갱신
        "sha256_raw": result.sha256,
        "last_changed_at": run_ts_iso,
        "last_checked_at": run_ts_iso,
        "raw_key": verified["raw_key"],
    })
    print(json.dumps({
        "changed": True,
        "raw_key": verified["raw_key"],
        "meta_key": verified["meta_key"],
        "attempts": result.attempts,
        "elapsed_ms": result.elapsed_ms,
    }, ensure_ascii = False))
    return {"changed": True, "raw_key": verified["raw_key"], "meta_key": verified["meta_key"]}