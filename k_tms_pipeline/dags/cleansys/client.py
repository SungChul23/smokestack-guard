import hashlib
import json
import time
import httpx
from dataclasses import dataclass
from datetime import datetime, timezone

URL = "https://apis.data.go.kr/B552584/cleansys/rltmMesureResult"
RETRY_STATUS = {429, 500, 502, 503, 504}  # Http 서버 오류
MAX_ATTEMPTS = 3                                    # 최대 시도 횟수
BACKOFF_SECONDS = (2, 5)                            # 처음 실패시 2초, 다음 실패시 5초 대기
TIMEOUT = httpx.Timeout(connect = 10.0, read = 60.0, write = 10.0, pool = 10.0)

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

# API Key를 이용해 Http Get 요청
def _get(api_key: str) -> httpx.Response:
    params = {"serviceKey": api_key, "type": "json"}    # API 요청에 필요한 쿼리 파라미터
    return httpx.get(URL, params = params, timeout = TIMEOUT)           # 지정 URL로 GET요청을 보내 응답 객체 반환

# API 호출 시도 및 결과 FetchResult로 반환 (실패시 재시도)
def fetch_snapshot(api_key: str) -> FetchResult:
    requested_at = datetime.now(timezone.utc).isoformat(timespec = "seconds")   # 요청 시작 시간 UTC 기준 문자열로 저장
    last_error = "알 수 없음" 

    for attempt in range(1, MAX_ATTEMPTS + 1):                          # 최대 수행 횟수만큼 재시도 시행
        start = time.perf_counter()                              # 시간 측정 시작
        try:
            resp = _get(api_key)                              # API 요청 시도
        except httpx.TransportError as exc:
            last_error = type(exc).__name__                        # 에러 유형 기록
        else:
            elapsed_ms = int((time.perf_counter() - start) * 1000)      # 응답 소요 시간 계산
            if resp.status_code == 200:                                 # 200(성공)일 시 FetchResult 객체 생성후 반환
                return FetchResult(
                    content = resp.content,
                    status_code = resp.status_code,
                    requested_at = requested_at,
                    elapsed_ms = elapsed_ms,
                    attempts = attempt,
                    sha256 = hashlib.sha256(resp.content).hexdigest()
                )
            if resp.status_code not in RETRY_STATUS:                   # 재시도 대상이 아닌 HTTP 에러시 즉시 예외 발생
                raise FetchError(f"HTTP {resp.status_code}")
            last_error = f"HTTP {resp.status_code}"               # 재시도 대상 에러일 시 상태 기록
        if attempt < MAX_ATTEMPTS:                                     # 다음 재시도 전 BACKOFF 시간만큼 대기
            time.sleep(BACKOFF_SECONDS[attempt - 1])
    raise FetchError(f"{MAX_ATTEMPTS}회 모두 실패: {last_error}")       # 모든 시도 실패시 예외 발생

# 수집된 데이터 구조, 내용 유효성 검사
def inspect_payload(content: bytes) -> dict:
    try:    
        data = json.loads(content)                                 # 데이터를 JSON 형태로 변환
        header = data["response"]["header"]                        # JSON 데이터 내 header, items 경로 접근
        items = data["response"]["body"]["items"]
    except (ValueError, KeyError, TypeError):                           # JSON 해석 실패, 키 누락, 타입 불일치 발생시
        return {"ok": False, "reason": "JSON 구조가 예상과 다름"}        # 즉시 실패 결과 반환 

    result_code = header.get("resultCode")                         # 결과 코드
    total_count = header.get("totalCount")                         # 전체 건수
    item_count = len(items)                                        # 실제 아이템 개수

    ok = result_code == "0" and total_count == item_count          # 결과 코드 = 0, 전체 건수 = 실제 아이템 건수가 일치하는지
    return {    
        "ok": ok,
        "result_code": result_code,
        "total_count": total_count,
        "item_count": item_count,
        "reason": None if ok else "resultCode 또는 건수 불일치"          # 검증 통과시 None, 실패시 원인 메시지     
    }