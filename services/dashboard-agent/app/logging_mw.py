"""요청 기록·사용자 활동을 JSON 한 줄로 표준 출력에 쓴다.

specs/a-platform/014-log-opensearch, contracts/log-format.md

CloudWatch(/tms/app/<앱>) → 라우터 → OpenSearch로 가서 그래프·검색에 쓰인다.
- 요청: {"log_type":"request","level","method","path"(라우트 원형),"status","duration_ms","sub"}
  상태 확인(/health 등)과 CORS 사전 요청(OPTIONS)은 남기지 않는다.
- 활동: log_activity(event, sub, **extra) → {"log_type":"activity","event","sub",...}
남기지 않는 것: 이메일·이름·초대 코드 입력값·질문 원문·요청 본문·쿼리 문자열·토큰.
dashboard-api와 dashboard-agent에 같은 내용으로 둔다(auth.py와 같은 방식).
"""

from __future__ import annotations

import base64
import json
import logging
import time

HEALTH_PATHS = {"/health", "/api/health", "/agent/health"}


class _StdoutHandler(logging.Handler):
    # 매번 sys.stdout을 써서 시험의 capsys로도 잡힌다
    def emit(self, record: logging.LogRecord) -> None:
        print(self.format(record), flush=True)


_out = logging.getLogger("tms.events")
if not _out.handlers:
    h = _StdoutHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    _out.addHandler(h)
    _out.setLevel(logging.INFO)
    _out.propagate = False


def emit(obj: dict) -> None:
    _out.info(json.dumps(obj, ensure_ascii=False))


def log_activity(event: str, sub: str | None, **extra) -> None:
    """사용자 활동 한 줄. extra에는 개인 정보가 아닌 값만(예: 즐겨찾기 대상 id)."""
    emit({"log_type": "activity", "event": event, "sub": sub, **extra})


def token_sub(authorization: str | None) -> str | None:
    """기록용으로만 토큰의 sub를 읽는다(서명 검증은 auth.py가 한다)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        payload = authorization.split(" ", 1)[1].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        sub = claims.get("sub")
        return sub if isinstance(sub, str) else None
    except (IndexError, ValueError):
        return None


def install(app) -> None:
    @app.middleware("http")
    async def request_log(request, call_next):
        if request.method == "OPTIONS" or request.url.path in HEALTH_PATHS:
            return await call_next(request)
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", None) or request.url.path
            emit({
                "log_type": "request",
                "level": "ERROR" if status >= 500 else "WARNING" if status >= 400 else "INFO",
                "method": request.method,
                "path": path,
                "status": status,
                "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
                "sub": token_sub(request.headers.get("authorization")),
            })
