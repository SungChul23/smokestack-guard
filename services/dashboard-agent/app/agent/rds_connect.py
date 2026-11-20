"""RDS 접속 풀 (spec 316). 읽기 전용 계정 `tms_app`을 IAM 인증으로 쓴다.

- 비밀번호가 없다. 연결을 새로 만들 때마다 짧게 유효한 IAM 토큰(15분)을 받아 비밀번호 자리에 넣는다.
  토큰은 로그·예외 문구에 쓰지 않는다.
- 서버 역할에 `rds-db:connect`(dbuser `tms_app`)가 있어야 한다(PR #63 T039, A).
- 연결마다 `default_transaction_read_only=on`과 `statement_timeout`을 건다.
  (계정 권한과 별개의 이중 방어)
- 환경 변수(서버가 뜰 때 SSM `/tms/app/config/*`에서 들어온다):
    DB_HOST(필수), DB_PORT(5432), DB_NAME(tms), DB_USER(tms_app), AWS_REGION(ap-northeast-2),
    DB_SSLROOTCERT(RDS 인증서 묶음 경로. 있으면 verify-full, 없으면 require)
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import boto3
import psycopg
from psycopg_pool import ConnectionPool

DEFAULT_USER = "tms_app"
DEFAULT_DB = "tms"
DEFAULT_REGION = "ap-northeast-2"
SESSION_OPTIONS = "-c default_transaction_read_only=on -c statement_timeout=8000"
WRITE_SESSION_OPTIONS = "-c statement_timeout=8000"  # 대화 상태 저장용(쓰기). 읽기 전용 옵션은 없다
CHECK_CONNECTION = ConnectionPool.check_connection  # 꺼내 쓰기 전에 연결이 살아 있는지 점검


def _auth_token(host: str, port: int, user: str, region: str) -> str:
    client = boto3.client("rds", region_name=region)
    return client.generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user, Region=region)


def iam_connection_class(host: str, port: int, user: str, region: str) -> type[psycopg.Connection]:
    """연결을 만들 때마다 새 IAM 토큰을 비밀번호로 넣는 연결 클래스."""

    class IamConnection(psycopg.Connection):
        @classmethod
        def connect(cls, conninfo: str = "", **kwargs):  # type: ignore[override]
            kwargs["password"] = _auth_token(host, port, user, region)
            return super().connect(conninfo, **kwargs)

    return IamConnection


def make_pool(
    env: Mapping[str, str] | None = None,
    *,
    read_only: bool = True,
    search_path: str | None = None,
    extra_kwargs: Mapping[str, object] | None = None,
    name: str | None = None,
) -> ConnectionPool:
    """풀을 만들어 연다. 서버가 뜰 때 DB가 닫혀 있어도 서비스는 뜬다(첫 질문에서 오류로 알린다).

    - read_only=True(기본): 관측 읽기용. 쓰기 풀(체크포인트 등)은 False로 만들고
      `search_path`로 `app`을 준다.
    - 끊어진 연결(DB 점검·장애·Multi-AZ 전환 뒤)은 꺼내 쓰기 전에 점검해서 버린다.
    """
    env = os.environ if env is None else env
    host = env.get("DB_HOST")
    if not host:
        raise RuntimeError("DB_HOST가 없다 (SSM /tms/app/config/db-host)")
    port = int(env.get("DB_PORT", "5432"))
    user = env.get("DB_USER", DEFAULT_USER)
    region = env.get("AWS_REGION", DEFAULT_REGION)
    options = SESSION_OPTIONS if read_only else WRITE_SESSION_OPTIONS
    if search_path:
        options += f" -c search_path={search_path}"
    kwargs: dict[str, object] = {
        "host": host,
        "port": port,
        "dbname": env.get("DB_NAME", DEFAULT_DB),
        "user": user,
        "connect_timeout": 5,
        "options": options,
        "autocommit": True,
    }
    kwargs.update(extra_kwargs or {})
    root_cert = env.get("DB_SSLROOTCERT")
    if root_cert:
        kwargs["sslmode"] = "verify-full"
        kwargs["sslrootcert"] = root_cert
    else:
        kwargs["sslmode"] = "require"
    pool = ConnectionPool(
        conninfo="",
        connection_class=iam_connection_class(host, port, user, region),
        kwargs=kwargs,
        min_size=1,
        max_size=4,
        max_lifetime=3000,
        timeout=10,
        check=CHECK_CONNECTION,
        name=name,
        open=False,
    )
    pool.open()
    return pool
