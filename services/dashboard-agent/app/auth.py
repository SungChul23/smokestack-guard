"""Cognito Access 토큰 검증 (specs/a-platform/009-service-infra, US3)

라우트 인자에 `user: CurrentUser`를 붙이면 로그인한 사용자 요청만 받는다.
- 검증: Cognito 공개키(JWKS) 서명, 만료, 발급자(iss), token_use=access, client_id
- 설정: COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID (서버가 뜰 때 SSM에서 들어옴)
- 로컬 개발: AUTH_DISABLED=1 이면 검증을 건너뛴다 (운영 서버에는 넣지 않는다)
"""

import os
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")


@lru_cache(maxsize=1)
def _jwks_client(issuer: str) -> jwt.PyJWKClient:
    # 공개키는 처음 한 번 받아 캐시한다 (NAT로 나감)
    return jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)


def verify_token(token: str) -> dict:
    pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    client_id = os.environ.get("COGNITO_CLIENT_ID")
    if not pool_id or not client_id:
        raise HTTPException(status_code=503, detail="인증 설정이 없다 (COGNITO_* 환경 변수)")

    issuer = f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}"
    try:
        key = _jwks_client(issuer).get_signing_key_from_jwt(token).key
        # Cognito Access 토큰에는 aud가 없고 client_id 클레임이 있다
        claims = jwt.decode(
            token, key, algorithms=["RS256"], issuer=issuer, options={"verify_aud": False}
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않다") from e

    if claims.get("token_use") != "access" or claims.get("client_id") != client_id:
        raise HTTPException(status_code=401, detail="이 앱의 Access 토큰이 아니다")
    return claims


def require_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    if os.environ.get("AUTH_DISABLED") == "1":
        return {"sub": "local-dev", "username": "local-dev"}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요하다")
    return verify_token(authorization.split(" ", 1)[1])


# 라우트에서: def handler(user: CurrentUser): ...
CurrentUser = Annotated[dict, Depends(require_user)]
