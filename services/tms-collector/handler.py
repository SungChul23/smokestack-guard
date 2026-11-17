import gzip
import hashlib
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

import bronze_marker as bm                  # 확정 표지(manifest.json, _SUCCESS) 형식

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

s3 = boto3.client("s3")                     # 핸들러 밖에서 생성해 재사용
ssm = boto3.client("ssm")
_api_key = None                             # 실행 환경이 살아 있는 동안 재사용


# API 데이터 호출 실패를 나타내는 사용자 정의 클래스
class FetchError(Exception):
    """
        호출 실패 class
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


# S3 업로드. ChecksumSHA256을 함께 보내 S3가 받은 내용이 다르면 업로드를 거부하게 한다(BadDigest).
# 일시 오류 재시도는 botocore 기본 재시도에 맡긴다. 그래도 실패하면 예외 → 상태 미갱신 → 다음 실행이 다시 저장.
def put_verified(key: str, body: bytes, content_type: str) -> None:
    s3.put_object(
        Bucket = BUCKET,
        Key = key,
        Body = body,
        ContentType = content_type,
        ChecksumSHA256 = bm.checksum_b64(body),
    )


# 수집 결과와 실행 시각을 받아 원문·메타를 S3에 저장, 결과 반환 (표지는 commit_snapshot에서)
def save_snapshot(result: FetchResult, run_ts: datetime) -> dict:
    prefix = build_prefix(run_ts)
    raw_key = bm.key(prefix, bm.RAW_NAME)
    meta_key = bm.key(prefix, bm.META_NAME)

    gz = gzip.compress(result.content, mtime = 0)
    put_verified(raw_key, gz, "application/gzip")

    inspected = inspect_payload(result.content)                     # 검증 실패 원문도 남기기 위해 저장 후 검증
    meta = build_meta(result, run_ts, raw_key, len(gz), inspected)
    meta_bytes = json.dumps(meta, ensure_ascii = False, indent = 2).encode("utf-8")
    put_verified(meta_key, meta_bytes, "application/json")
    return {"raw_key": raw_key, "meta_key": meta_key, "inspect": inspected, "gz": gz, "meta_bytes": meta_bytes}


# 원문 점검을 통과한 폴더에 manifest.json → _SUCCESS 순으로 확정 표지를 남긴다. _SUCCESS가 폴더의 마지막 파일이다.
def commit_snapshot(prefix: str, gz: bytes, meta_bytes: bytes, raw_sha256: str) -> None:
    manifest = bm.build_manifest(gz, meta_bytes, raw_sha256, bm.now_iso())
    put_verified(bm.key(prefix, bm.MANIFEST_NAME), manifest, "application/json")
    put_verified(bm.key(prefix, bm.SUCCESS_NAME), b"", "application/octet-stream")


# 같은 run_ts 폴더가 이미 완성(_SUCCESS 있음)됐으면 그 manifest의 raw_sha256, 아니면 None
# Lambda 자동 재실행은 같은 run_ts로 같은 폴더에 쓰므로, 완성된 폴더를 덮어쓰지 않으려고 확인한다.
def find_committed(prefix: str) -> str | None:
    try:
        s3.head_object(Bucket = BUCKET, Key = bm.key(prefix, bm.SUCCESS_NAME))
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code not in ("404", "NoSuchKey", "NotFound", "403", "AccessDenied"):  # ListBucket 권한이 없으면 없는 키도 403
            raise
        return None
    body = s3.get_object(Bucket = BUCKET, Key = bm.key(prefix, bm.MANIFEST_NAME))["Body"].read()
    return json.loads(body)["raw_sha256"]


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

    prefix = build_prefix(run_ts)
    committed_sha = find_committed(prefix)                          # 같은 run_ts 재실행이면 앞 시도가 완성했는지 확인
    if committed_sha is not None:
        raw_key = bm.key(prefix, bm.RAW_NAME)
        if committed_sha == result.sha256:                          # 앞 시도가 표지까지 쓰고 상태 저장에서 끊긴 경우
            save_state({
                "sha256_raw": result.sha256,
                "last_changed_at": run_ts_iso,
                "last_checked_at": run_ts_iso,
                "raw_key": raw_key,
            })
            marker = "already_committed"
        else:                                                       # 완성된 폴더는 덮어쓰지 않는다. 상태를 그대로 두면 다음 실행이 새 폴더에 저장
            marker = "skipped_committed_folder"
        print(json.dumps({"changed": True, "marker": marker, "raw_key": raw_key,
                          "attempts": result.attempts, "elapsed_ms": result.elapsed_ms}, ensure_ascii = False))
        return {"changed": True, "marker": marker, "raw_key": raw_key}

    saved = save_snapshot(result, run_ts)

    inspected = saved["inspect"]
    if not inspected["ok"]:                                         # 예외를 던져야 Lambda 실패로 집계됨
        raise RuntimeError(                                         # 표지·상태를 쓰지 않아 마지막 정상 응답과 계속 비교
            f"원문 점검 실패: {inspected.get('reason')} "
            f"(total = {inspected.get('total_count')}, items = {inspected.get('item_count')})"
        )

    commit_snapshot(prefix, saved["gz"], saved["meta_bytes"], result.sha256)

    save_state({                                                    # 원문, 메타, 표지 저장이 끝난 뒤 마지막에 갱신
        "sha256_raw": result.sha256,
        "last_changed_at": run_ts_iso,
        "last_checked_at": run_ts_iso,
        "raw_key": saved["raw_key"],
    })
    summary = {"raw_key": saved["raw_key"], "meta_key": saved["meta_key"], "inspect": inspected, "marker": "written"}
    print(json.dumps({"changed": True, **summary, "attempts": result.attempts, "elapsed_ms": result.elapsed_ms}, ensure_ascii = False))
    return {"changed": True, **summary}
