import pytest
from conftest import make_data
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.agent import api
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import SiteResolver
from app.agent.service import AgentService
from app.main import app


@pytest.fixture
def client(monkeypatch, clock):
    data = make_data()
    resolver = SiteResolver(sites_from(data))
    api.set_service(
        AgentService(RuleExtractor(resolver), data, InMemorySaver(), clock, "rule-dev", resolver)
    )
    monkeypatch.setenv("AUTH_DISABLED", "1")
    yield TestClient(app)
    api.set_service(None)


def test_chat_requires_login(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    response = TestClient(app).post("/agent/chat", json={"message": "안녕"})
    assert response.status_code == 401


def test_chat_returns_the_contract_shape(client):
    response = client.post("/agent/chat", json={"message": "가나에너지 굴뚝 1 어제 NOx 평균"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ANSWERED" and body["conversation_id"] and body["request_id"]
    assert body["data_as_of"] == "2026-11-10T23:30:00+09:00"
    assert body["parts"][0]["numbers"][0]["unit"] == "ppm"
    assert body["trace"]["turn_type"] == "MESSAGE"


def test_card_round_trip_over_http(client):
    first = client.post("/agent/chat", json={"message": "가나에너지 굴뚝 1 NOx 평균"}).json()
    assert first["status"] == "NEEDS_INPUT"
    second = client.post(
        "/agent/chat",
        json={
            "conversation_id": first["conversation_id"],
            "resume": {"card_id": first["card"]["card_id"], "option_id": "yesterday"},
        },
    ).json()
    assert second["status"] == "ANSWERED" and second["trace"]["turn_type"] == "RESUME"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": "a", "resume": {"card_id": "c", "option_id": "o"}},
        {"message": "a", "context": {"allowedStackIds": ["1:1"]}},
    ],
)
def test_bad_bodies_are_422(client, body):
    assert client.post("/agent/chat", json=body).status_code == 422
