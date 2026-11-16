from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_api_health_under_prefix():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["app"] == "api"


def test_db_check_without_db_is_503(monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    assert client.get("/api/db-check").status_code == 503
