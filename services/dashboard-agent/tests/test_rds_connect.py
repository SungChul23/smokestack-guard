"""RDS 접속 설정 시험 (spec 316). 실제로 접속하지 않는다."""

import psycopg
import pytest

import app.agent.rds_connect as rc


class FakeRdsClient:
    def __init__(self, calls: list[dict]) -> None:
        self._calls = calls

    def generate_db_auth_token(self, **kwargs) -> str:
        self._calls.append(kwargs)
        return "TOKEN-1"


def test_each_new_connection_gets_a_fresh_iam_token_as_password(monkeypatch):
    token_calls: list[dict] = []
    monkeypatch.setattr(rc.boto3, "client", lambda *a, **k: FakeRdsClient(token_calls))
    seen: list[dict] = []

    def fake_connect(cls, conninfo="", **kwargs):
        seen.append(kwargs)
        return "connection"

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(fake_connect))
    klass = rc.iam_connection_class("db.example", 5432, "tms_app", "ap-northeast-2")
    assert klass.connect("", host="db.example", user="tms_app") == "connection"
    assert klass.connect("", host="db.example", user="tms_app") == "connection"
    assert [kw["password"] for kw in seen] == ["TOKEN-1", "TOKEN-1"]
    assert len(token_calls) == 2  # 연결마다 새로 받는다
    assert token_calls[0] == {
        "DBHostname": "db.example",
        "Port": 5432,
        "DBUsername": "tms_app",
        "Region": "ap-northeast-2",
    }


def test_pool_requires_a_host():
    with pytest.raises(RuntimeError, match="DB_HOST"):
        rc.make_pool({})


def test_pool_is_configured_read_only_with_tls_and_defaults(monkeypatch):
    captured: dict = {}

    class FakePool:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def open(self) -> None:
            captured["opened"] = True

    monkeypatch.setattr(rc, "ConnectionPool", FakePool)
    rc.make_pool({"DB_HOST": "db.example"})
    kw = captured["kwargs"]
    assert (kw["host"], kw["port"], kw["dbname"], kw["user"]) == (
        "db.example",
        5432,
        "tms",
        "tms_app",
    )
    assert kw["sslmode"] == "require"
    assert "default_transaction_read_only=on" in kw["options"]
    assert "statement_timeout" in kw["options"]
    assert "password" not in kw  # 비밀번호는 연결할 때 토큰으로만 들어간다
    assert captured["open"] is False and captured["opened"] is True


def test_root_cert_switches_to_verify_full(monkeypatch):
    captured: dict = {}

    class FakePool:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def open(self) -> None:
            pass

    monkeypatch.setattr(rc, "ConnectionPool", FakePool)
    rc.make_pool(
        {"DB_HOST": "db.example", "DB_SSLROOTCERT": "/certs/global-bundle.pem", "DB_USER": "x"}
    )
    kw = captured["kwargs"]
    assert kw["sslmode"] == "verify-full"
    assert kw["sslrootcert"] == "/certs/global-bundle.pem"
    assert kw["user"] == "x"


def test_write_pool_is_not_read_only_and_uses_the_app_schema(monkeypatch):
    """대화 상태 저장용 풀(spec 319): 읽기 전용 옵션이 없고 `app` 스키마를 기본으로 쓴다."""
    captured: dict = {}

    class FakePool:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def open(self) -> None:
            pass

    monkeypatch.setattr(rc, "ConnectionPool", FakePool)
    rc.make_pool(
        {"DB_HOST": "db.example"},
        read_only=False,
        search_path="app",
        extra_kwargs={"prepare_threshold": 0},
        name="agent-state",
    )
    kw = captured["kwargs"]
    assert "default_transaction_read_only" not in kw["options"]
    assert "search_path=app" in kw["options"]
    assert "statement_timeout" in kw["options"]
    assert kw["prepare_threshold"] == 0 and kw["autocommit"] is True
    assert captured["name"] == "agent-state"


def test_pools_check_connections_before_handing_them_out(monkeypatch):
    """DB 점검·장애·Multi-AZ 전환 뒤 끊어진 연결을 쓰지 않도록 꺼내기 전에 점검한다."""
    captured: dict = {}

    class FakePool:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def open(self) -> None:
            pass

    monkeypatch.setattr(rc, "ConnectionPool", FakePool)
    rc.make_pool({"DB_HOST": "db.example"})
    assert captured["check"] is rc.CHECK_CONNECTION
