from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_agent_health_under_prefix():
    body = client.get("/agent/health").json()
    assert body["status"] == "ok"
    assert body["app"] == "agent"
