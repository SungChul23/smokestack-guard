"""에이전트 요청 기록 (014 T019): JSON 한 줄, 상태 확인 제외."""

import json

from fastapi.testclient import TestClient

from app.main import app
from tests.test_auth import cognito as _cognito  # noqa: F401  (autouse 픽스처)
from tests.test_auth import token

client = TestClient(app)


def test_agent_request_logged_and_health_skipped(capsys):
    client.get("/agent/health")
    client.get("/agent/me", headers={"Authorization": f"Bearer {token()}"})
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    req = [x for x in lines if x.get("log_type") == "request"]
    assert len(req) == 1
    assert (req[0]["path"], req[0]["status"], req[0]["sub"]) == ("/agent/me", 200, "user-1")
