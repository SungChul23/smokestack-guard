"""테스트 공용: dict 기반 가짜 S3·SSM과 handler 로딩.

실제 AWS를 부르지 않는다. 가짜 S3는 이 기능에 필요한 S3 동작만 흉내 낸다.
- ChecksumSHA256이 내용과 다르면 BadDigest로 거부
- IfNoneMatch="*"이고 키가 있으면 PreconditionFailed(412)로 거부
- 없는 키 head_object → 404, get_object → NoSuchKey
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import sys

import pytest
from botocore.exceptions import ClientError


def _error(code: str, op: str, status: int = 400) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, op)


class _Paginator:
    def __init__(self, s3: FakeS3):
        self.s3 = s3

    def paginate(self, Bucket: str, Prefix: str = ""):
        yield self.s3.list_objects_v2(Bucket=Bucket, Prefix=Prefix)


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str | None] = {}
        self.put_log: list[str] = []          # put에 성공한 키 순서
        self.put_kwargs: dict[str, dict] = {}  # 키별 마지막 put 인자 (Body 제외)
        self.fail_on_put: dict[str, str] = {}  # 키 → 오류 코드 (그 키 put을 실패시킴)

    # --- 쓰기 ---
    def put_object(self, Bucket: str, Key: str, Body: bytes = b"", ContentType: str | None = None,
                   ChecksumSHA256: str | None = None, IfNoneMatch: str | None = None):
        if Key in self.fail_on_put:
            raise _error(self.fail_on_put[Key], "PutObject")
        if ChecksumSHA256 is not None:
            actual = base64.b64encode(hashlib.sha256(Body).digest()).decode()
            if actual != ChecksumSHA256:
                raise _error("BadDigest", "PutObject")
        if IfNoneMatch == "*" and Key in self.objects:
            raise _error("PreconditionFailed", "PutObject", 412)
        self.objects[Key] = bytes(Body)
        self.content_types[Key] = ContentType
        self.put_log.append(Key)
        self.put_kwargs[Key] = {"ContentType": ContentType, "ChecksumSHA256": ChecksumSHA256,
                                "IfNoneMatch": IfNoneMatch}
        return {}

    # --- 읽기 ---
    def get_object(self, Bucket: str, Key: str):
        if Key not in self.objects:
            raise _error("NoSuchKey", "GetObject", 404)
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket: str, Key: str):
        if Key not in self.objects:
            raise _error("404", "HeadObject", 404)
        return {"ContentLength": len(self.objects[Key])}

    def list_objects_v2(self, Bucket: str, Prefix: str = ""):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        return {"Contents": [{"Key": k, "Size": len(self.objects[k])} for k in keys]}

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        return _Paginator(self)


class FakeSSM:
    def get_parameter(self, Name: str, WithDecryption: bool = False):
        return {"Parameter": {"Value": "test-api-key"}}


def make_payload(items: int = 3, total: int | None = None, code: str = "0", tag: str = "a") -> bytes:
    """CleanSYS 응답 모양의 가짜 원문. tag를 바꾸면 해시가 달라진다."""
    body = {
        "response": {
            "header": {"resultCode": code, "totalCount": items if total is None else total},
            "body": {"items": [{"stack_code": f"S{i}", "nox_mesure_value": "1.0", "tag": tag} for i in range(items)]},
        }
    }
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


@pytest.fixture
def s3() -> FakeS3:
    return FakeS3()


@pytest.fixture
def handler(monkeypatch, s3):
    """환경 변수를 넣고 handler를 새로 import한 뒤 S3·SSM을 가짜로 바꾼다."""
    monkeypatch.setenv("BRONZE_BUCKET", "test-bucket")
    monkeypatch.setenv("API_KEY_PARAMETER", "/test/api-key")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-2")
    sys.modules.pop("handler", None)
    module = importlib.import_module("handler")
    monkeypatch.setattr(module, "s3", s3)
    monkeypatch.setattr(module, "ssm", FakeSSM())
    monkeypatch.setattr(module, "_api_key", None)
    return module


@pytest.fixture
def fetch(monkeypatch, handler):
    """handler.fetch_snapshot이 주어진 원문을 돌려주게 한다. fetch(content) 형태로 쓴다."""

    def _set(content: bytes):
        result = handler.FetchResult(
            content=content,
            status_code=200,
            requested_at="2026-11-10T06:00:01+00:00",
            elapsed_ms=120,
            attempts=1,
            sha256=hashlib.sha256(content).hexdigest(),
        )
        monkeypatch.setattr(handler, "fetch_snapshot", lambda api_key: result)
        return result

    return _set
