"""초대 코드 확인 (013 contracts §4): 통과·공백·NFC·틀림·시도 제한·설정 없음·로그에 값 없음."""

import logging
import unicodedata

import pytest
from fastapi.testclient import TestClient

from app import invite
from app.main import app
from tests.test_auth import cognito as _cognito  # noqa: F401  (autouse 픽스처)
from tests.test_auth import token  # 같은 가짜 Cognito 설정을 쓴다

ANSWER = "수료축하 2026"
client = TestClient(app)


class FakeSSM:
    def __init__(self, value=ANSWER, fail=False):
        self.value, self.fail, self.calls = value, fail, 0

    def get_parameter(self, Name, WithDecryption):  # noqa: N803
        self.calls += 1
        assert WithDecryption is True
        if self.fail:
            raise RuntimeError("AccessDenied")
        return {"Parameter": {"Value": self.value}}


class FakeCognito:
    def __init__(self):
        self.added = []

    def admin_add_user_to_group(self, UserPoolId, Username, GroupName):  # noqa: N803
        self.added.append((UserPoolId, Username, GroupName))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(monkeypatch):
    ssm, cog, clock = FakeSSM(), FakeCognito(), Clock()
    monkeypatch.setattr(invite, "checker", invite.InviteChecker(ssm, cog, clock))
    return ssm, cog, clock


def post(code, **claims):
    return client.post("/api/invite", json={"code": code},
                       headers={"Authorization": f"Bearer {token(**claims)}"})


def test_right_code_adds_to_members(env):
    _, cog, _ = env
    r = post("  수료축하 2026 ")
    assert r.status_code == 200 and r.json() == {"member": True}
    assert cog.added == [("ap-northeast-2_TEST", "user-1", "members")]


def test_decomposed_hangul_input_matches(env):
    assert post(unicodedata.normalize("NFD", ANSWER)).status_code == 200


def test_wrong_code_then_limited_then_allowed_after_window(env):
    _, cog, clock = env
    for _ in range(5):
        r = post("틀림")
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_code"
    r = post(ANSWER)  # 맞아도 제한 중에는 확인하지 않는다
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_attempts"
    clock.t += 601
    assert post(ANSWER).status_code == 200
    assert len(cog.added) == 1


def test_limit_is_per_user(env):
    for _ in range(5):
        post("틀림")
    assert post(ANSWER, sub="user-2", username="user-2").status_code == 200


def test_missing_parameter_lets_nobody_in(env, monkeypatch):
    ssm, cog, _ = env
    ssm.fail = True
    r = post(ANSWER)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "not_configured"
    assert cog.added == []


def test_answer_is_cached_for_five_minutes(env):
    ssm, _, clock = env
    post("a"); post("b")  # noqa: E702
    assert ssm.calls == 1
    clock.t += 301
    post("c")
    assert ssm.calls == 2


def test_already_member_is_ok_without_check(env):
    ssm, cog, _ = env
    assert post("아무거나", **{"cognito:groups": ["members"]}).status_code == 200
    assert ssm.calls == 0 and cog.added == []


def test_code_value_never_logged(env, caplog):
    caplog.set_level(logging.DEBUG)
    post("비밀-입력값")
    post(ANSWER)
    assert "비밀-입력값" not in caplog.text and ANSWER not in caplog.text
    assert "result=invalid" in caplog.text and "result=ok" in caplog.text


def test_invite_requires_login(env):
    assert client.post("/api/invite", json={"code": ANSWER}).status_code == 401

