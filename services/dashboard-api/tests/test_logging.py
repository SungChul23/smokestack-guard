"""요청 기록·사용자 활동 (014 T017·T023·T026).

JSON 한 줄, 라우트 원형, 상태 확인 제외, 개인 정보 없음.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import invite
from app.main import app
from tests.test_auth import cognito as _cognito  # noqa: F401  (autouse 픽스처)
from tests.test_auth import token
from tests.test_invite import FakeCognito, FakeSSM

client = TestClient(app)


def events(capsys) -> list[dict]:
    out = []
    for line in capsys.readouterr().out.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "log_type" in obj:
            out.append(obj)
    return out


def test_request_line_has_route_template_status_duration_sub(capsys):
    client.get("/api/me", headers={"Authorization": f"Bearer {token()}"})
    req = [e for e in events(capsys) if e["log_type"] == "request"]
    assert len(req) == 1
    r = req[0]
    got = (r["method"], r["path"], r["status"], r["level"], r["sub"])
    assert got == ("GET", "/api/me", 200, "INFO", "user-1")
    assert isinstance(r["duration_ms"], float)


def test_health_and_preflight_are_not_logged(capsys):
    client.get("/health")
    client.get("/api/health")
    pre = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    client.options("/api/me", headers=pre)
    assert [e for e in events(capsys) if e["log_type"] == "request"] == []


def test_error_levels(capsys):
    client.get("/api/me")  # 토큰 없음 401
    r = [e for e in events(capsys) if e["log_type"] == "request"][0]
    assert (r["status"], r["level"], r["sub"]) == (401, "WARNING", None)


def test_unknown_path_keeps_no_query_string(capsys):
    client.get("/api/nope?email=someone@example.com")
    r = [e for e in events(capsys) if e["log_type"] == "request"][0]
    assert r["path"] == "/api/nope" and "example.com" not in json.dumps(r)


@pytest.fixture
def invite_env(monkeypatch):
    monkeypatch.setattr(invite, "checker", invite.InviteChecker(FakeSSM(), FakeCognito()))


def test_activity_events_without_personal_data(capsys, invite_env):
    hdr = {"Authorization": f"Bearer {token(email='person@example.com')}"}
    client.get("/api/me", headers=hdr)
    client.post("/api/invite", json={"code": "틀린-코드-입력값"}, headers=hdr)
    for _ in range(5):
        client.post("/api/invite", json={"code": "틀림"}, headers=hdr)
    acts = [e for e in events(capsys) if e["log_type"] == "activity"]
    assert [a["event"] for a in acts][:2] == ["session", "invite_fail"]
    assert acts[-1]["event"] == "invite_limited"
    blob = json.dumps(acts, ensure_ascii=False)
    assert "person@example.com" not in blob and "틀린-코드-입력값" not in blob
    assert all(a["sub"] == "user-1" for a in acts)


def test_invite_ok_event(capsys, invite_env):
    hdr = {"Authorization": f"Bearer {token()}"}
    from tests.test_invite import ANSWER

    client.post("/api/invite", json={"code": ANSWER}, headers=hdr)
    assert [a["event"] for a in events(capsys) if a["log_type"] == "activity"] == ["invite_ok"]
