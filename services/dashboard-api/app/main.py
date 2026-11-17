"""대시보드 API 최소 앱 (배포 길 확인용). D가 이어서 개발한다.

계약: specs/a-platform/009-service-infra/contracts/app-runtime.md
- 포트 8000, 상태 확인 GET /health
- 모든 API 경로는 /api/ 아래 (ALB가 접두사를 떼지 않는다)
- 로그인 필수: 운영 확인용(/health, /api/health, /api/db-check)만 공개.
  새 라우트는 인자에 `user: CurrentUser`를 붙인다 (app/auth.py)
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.auth import CurrentUser

app = FastAPI(title="tms dashboard api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("APP_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


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
def me(user: CurrentUser) -> dict:
    """로그인 확인용. 화면이 처음 서버 인증을 확인할 때 부른다."""
    return {"sub": user.get("sub"), "username": user.get("username")}
