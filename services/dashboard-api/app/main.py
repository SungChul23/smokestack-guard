"""대시보드 API 최소 앱 (배포 길 확인용). D가 이어서 개발한다.

계약: specs/a-platform/009-service-infra/contracts/app-runtime.md
- 포트 8000, 상태 확인 GET /health
- 모든 API 경로는 /api/ 아래 (ALB가 접두사를 떼지 않는다)
- 공개: 운영 확인용(/health, /api/health, /api/db-check)
- 로그인만: /api/me, /api/invite (초대 코드 전, 013)
- 그 밖: 새 라우트는 인자에 `user: CurrentUser`(로그인 + members)를 붙인다 (app/auth.py)
  계약: specs/a-platform/013-google-login-invite/contracts/auth-api.md
"""

import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import dashboard, invite, logging_mw
from app.auth import LoggedInUser, is_member
from app.db import DbUnavailable
from app.logging_mw import log_activity

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("tms.api")

app = FastAPI(title="tms dashboard api")
logging_mw.install(app)  # 요청마다 JSON 한 줄 (014)

app.add_middleware(GZipMiddleware, minimum_size=1000)  # 하루치 응답(약 3MB)을 줄여 보낸다
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("APP_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(DbUnavailable)
async def db_unavailable(_req: Request, e: DbUnavailable) -> JSONResponse:
    detail = {"code": "db_unavailable", "message": str(e)}
    return JSONResponse(status_code=503, content={"detail": detail})


app.include_router(dashboard.router)  # 화면용 읽기 라우트·즐겨찾기 (로그인 회원만)


@app.get("/health")
def health() -> dict:
    """ALB 상태 확인. DB·외부 서비스를 부르지 않는다."""
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "app": "api", "version": os.environ.get("APP_VERSION", "local")}


REGION = os.environ.get("AWS_REGION", "ap-northeast-2")


def _db_password(secret_arn: str) -> str:
    import boto3

    # boto3는 AWS_REGION을 읽지 않으므로 리전을 직접 준다
    client = boto3.client("secretsmanager", region_name=REGION)
    secret = client.get_secret_value(SecretId=secret_arn)
    return json.loads(secret["SecretString"])["password"]


@app.get("/api/db-check")
def db_check() -> dict:
    """서버 → RDS 연결 확인 (SELECT 1). DB가 꺼져 있거나 연결에 실패하면 503 + 실패 단계."""
    host = os.environ.get("DB_HOST")
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not host or not secret_arn:
        raise HTTPException(status_code=503, detail="DB가 꺼져 있다 (DB_HOST 없음)")

    try:
        password = _db_password(secret_arn)
    except Exception as e:  # 비밀 읽기 실패 (권한·리전·네트워크)
        raise HTTPException(status_code=503, detail=f"비밀 읽기 실패: {type(e).__name__}") from e

    import psycopg

    try:
        with psycopg.connect(
            host=host,
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ.get("DB_NAME", "tms"),
            user="tms_admin",
            password=password,
            connect_timeout=5,
            sslmode="require",
        ) as conn:
            value = conn.execute("SELECT 1").fetchone()[0]
    except psycopg.Error as e:  # 연결·인증 실패
        raise HTTPException(status_code=503, detail=f"DB 연결 실패: {type(e).__name__}") from e
    return {"status": "ok", "select_1": value}


@app.get("/api/me")
def me(user: LoggedInUser) -> dict:
    """로그인·자격 확인. 화면은 member가 false면 초대 코드 화면을 보여 준다 (013)."""
    log_activity("session", user.get("sub"))  # 화면 진입 = 하루 접속자 (014)
    return {"sub": user.get("sub"), "member": is_member(user)}


class InviteRequest(BaseModel):
    code: str


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@app.post("/api/invite")
def join(body: InviteRequest, user: LoggedInUser) -> dict:
    """초대 코드가 맞으면 members 그룹에 넣는다. 화면은 이어서 토큰을 새로 받는다 (013 R4)."""
    sub = user.get("sub")
    if is_member(user):
        return {"member": True}
    try:
        ok = invite.checker.check(sub, body.code)
    except invite.TooManyAttempts:
        log.info("invite sub=%s result=limited", sub)
        log_activity("invite_limited", sub)
        raise _error(429, "too_many_attempts", "잠시 뒤 다시 시도") from None
    except invite.NotConfigured as e:
        log.warning("invite sub=%s result=not_configured reason=%s", sub, e)
        raise _error(503, "not_configured", "초대 코드 설정이 없다") from None
    if not ok:
        log.info("invite sub=%s result=invalid", sub)
        log_activity("invite_fail", sub)
        raise _error(400, "invalid_code", "초대 코드가 맞지 않는다")
    invite.checker.add_to_members(user.get("username"))
    log.info("invite sub=%s result=ok", sub)
    log_activity("invite_ok", sub)
    return {"member": True}
