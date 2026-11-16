"""대시보드 API 최소 앱 (배포 길 확인용). D가 이어서 개발한다.

계약: specs/a-platform/009-service-infra/contracts/app-runtime.md
- 포트 8000, 상태 확인 GET /health
- 모든 API 경로는 /api/ 아래 (ALB가 접두사를 떼지 않는다)
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="tms dashboard api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("APP_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """ALB 상태 확인. DB·외부 서비스를 부르지 않는다."""
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "app": "api", "version": os.environ.get("APP_VERSION", "local")}


def _db_password(secret_arn: str) -> str:
    import boto3

    client = boto3.client("secretsmanager")
    secret = client.get_secret_value(SecretId=secret_arn)
    return json.loads(secret["SecretString"])["password"]


@app.get("/api/db-check")
def db_check() -> dict:
    """서버 → RDS 연결 확인 (SELECT 1). DB가 꺼져 있으면 503."""
    host = os.environ.get("DB_HOST")
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not host or not secret_arn:
        raise HTTPException(status_code=503, detail="DB가 꺼져 있다 (DB_HOST 없음)")

    import psycopg

    with psycopg.connect(
        host=host,
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "tms"),
        user="tms_admin",
        password=_db_password(secret_arn),
        connect_timeout=5,
        sslmode="require",
    ) as conn:
        value = conn.execute("SELECT 1").fetchone()[0]
    return {"status": "ok", "select_1": value}
