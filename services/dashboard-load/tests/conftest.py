"""테스트 도구 (spec 012). 실제 원본 값은 쓰지 않는다.

DB 테스트는 PostgreSQL 16 + pgvector가 필요하다. 환경 변수가 없으면 건너뛴다.
    TEST_PG_HOST(기본 localhost) TEST_PG_PORT(기본 55432) TEST_PG_USER(postgres) TEST_PG_PASSWORD
    로컬: docker run -d --name tms-pg-test -e POSTGRES_PASSWORD=test -p 55432:5432 pgvector/pgvector:pg16
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

BUCKET = "smokestack-tms-raw-952900391026"
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


class FakeS3:
    """메모리 dict 가짜 S3. read_bronze가 쓰는 메서드만."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body=b"", ContentType=None):
        self.objects[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.encode("utf-8")
        return {}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix=""):
        keys = sorted(k for b, k in self.objects if b == Bucket and k.startswith(Prefix))
        yield {"Contents": [{"Key": k} for k in keys]}


@pytest.fixture
def fake_s3():
    return FakeS3()


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def _pg_params():
    pw = os.environ.get("TEST_PG_PASSWORD")
    if not pw:
        return None
    return {
        "host": os.environ.get("TEST_PG_HOST", "localhost"),
        "port": int(os.environ.get("TEST_PG_PORT", "55432")),
        "user": os.environ.get("TEST_PG_USER", "postgres"),
        "password": pw,
    }


@pytest.fixture
def pg():
    """테스트마다 새 데이터베이스에 마이그레이션 001~004를 적용한 연결."""
    params = _pg_params()
    if params is None:
        pytest.skip("TEST_PG_PASSWORD가 없어 DB 테스트를 건너뛴다")
    import db

    name = f"t_{uuid.uuid4().hex[:12]}"
    admin = db.connect(**params, database="postgres", tls=False)
    admin.run(f"CREATE DATABASE {name}")
    conn = db.connect(**params, database=name, tls=False)
    db.migrate(conn, MIGRATIONS)
    try:
        yield conn
    finally:
        conn.close()
        admin.run(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()
