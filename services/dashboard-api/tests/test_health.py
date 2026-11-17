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


def test_db_check_secret_failure_is_503(monkeypatch):
    from app import main

    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-2:1:secret:rds!db-x")

    def boom(_arn):
        raise RuntimeError("no access")

    monkeypatch.setattr(main, "_db_password", boom)
    r = client.get("/api/db-check")
    assert r.status_code == 503
    assert "비밀 읽기 실패" in r.json()["detail"]
