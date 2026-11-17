"""Cognito Access 토큰 검증: 서명·발급자·token_use·client_id, 토큰 없음 401."""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import auth
from app.main import app

POOL = "ap-northeast-2_TEST"
CLIENT = "test-client"
ISSUER = f"https://cognito-idp.ap-northeast-2.amazonaws.com/{POOL}"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ME = "/api/me"

client = TestClient(app)


@pytest.fixture(autouse=True)
def cognito(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", POOL)
    monkeypatch.setenv("COGNITO_CLIENT_ID", CLIENT)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    fake = SimpleNamespace(
        get_signing_key_from_jwt=lambda _t: SimpleNamespace(key=KEY.public_key())
    )
    monkeypatch.setattr(auth, "_jwks_client", lambda _issuer: fake)


def token(**over) -> str:
    claims = {
        "sub": "user-1",
        "username": "user-1",
        "iss": ISSUER,
        "token_use": "access",
        "client_id": CLIENT,
        "exp": int(time.time()) + 300,
    } | over
    return jwt.encode(claims, KEY, algorithm="RS256")


def get(tok: str | None):
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    return client.get(ME, headers=headers)


def test_valid_token():
    r = get(token())
    assert r.status_code == 200
    assert r.json()["sub"] == "user-1"


def test_no_token_is_401():
    assert get(None).status_code == 401


@pytest.mark.parametrize(
    "over",
    [
        {"iss": "https://cognito-idp.ap-northeast-2.amazonaws.com/other"},
        {"token_use": "id"},
        {"client_id": "other-client"},
        {"exp": int(time.time()) - 10},
    ],
)
def test_wrong_claims_are_401(over):
    assert get(token(**over)).status_code == 401


def test_health_is_public():
    assert client.get("/health").status_code == 200
