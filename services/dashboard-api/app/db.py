"""RDS 연결 (읽기 라우트용).

- 기본 계정은 tms_app(IAM 인증): ref·obs 읽기, app·rag 읽기·쓰기(012 data-model §7).
  서버 역할에 rds-db:connect가 있어야 한다(A).
- 환경 변수 DB_USER=tms_admin 이면 관리자 비밀(Secrets Manager) 방식으로 접속한다.
  권한이 열리기 전 임시·로컬 확인용이다.
- 연결은 요청마다 새로 연다(짧은 읽기). 결과는 라우트에서 30분 갱신 주기에 맞춰 캐시한다.
"""

import json
import os
import time
from collections.abc import Iterator

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_PASSWORD_TTL = 300  # 비밀번호는 30일마다 바뀐다. 5분 캐시, 인증 오류가 나면 다시 읽는다
_password: dict = {"value": None, "at": 0.0}


class DbUnavailable(Exception):
    """DB가 꺼져 있거나(DB_HOST 없음) 연결할 수 없다."""


def _secret_password(secret_arn: str, *, refresh: bool = False) -> str:
    now = time.monotonic()
    if not refresh and _password["value"] and now - _password["at"] < _PASSWORD_TTL:
        return _password["value"]
    import boto3

    client = boto3.client("secretsmanager", region_name=REGION)
    value = json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])["password"]
    _password.update(value=value, at=now)
    return value


def _iam_token(host: str, port: int, user: str) -> str:
    import boto3

    return boto3.client("rds", region_name=REGION).generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername=user, Region=REGION
    )


def connect():
    """psycopg 연결을 돌려준다. 호출한 쪽이 닫는다."""
    import psycopg

    host = os.environ.get("DB_HOST")
    if not host:
        raise DbUnavailable("DB가 꺼져 있다 (DB_HOST 없음)")
    port = int(os.environ.get("DB_PORT", "5432"))
    user = os.environ.get("DB_USER", "tms_app")
    params = dict(
        host=host,
        port=port,
        dbname=os.environ.get("DB_NAME", "tms"),
        user=user,
        connect_timeout=5,
        sslmode="require",
    )
    try:
        if user == "tms_admin":
            arn = os.environ.get("DB_SECRET_ARN")
            if not arn:
                raise DbUnavailable("DB_SECRET_ARN 없음")
            try:
                return psycopg.connect(password=_secret_password(arn), **params)
            except psycopg.OperationalError:
                return psycopg.connect(password=_secret_password(arn, refresh=True), **params)
        return psycopg.connect(password=_iam_token(host, port, user), **params)
    except DbUnavailable:
        raise
    except Exception as e:  # 연결·인증·비밀 읽기 실패
        raise DbUnavailable(f"DB 연결 실패: {type(e).__name__}") from e


def get_conn() -> Iterator:
    """FastAPI 의존성: 요청 하나에 연결 하나."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
