"""Cognito Access 토큰 검증 + 서비스 자격 확인 (009 US3, 013)

라우트 종류 (specs/a-platform/013-google-login-invite/contracts/auth-api.md):
- 기본: 인자에 `user: CurrentUser` → 로그인 + 초대 코드를 통과한 회원(그룹 members)만
- 로그인만: `user: LoggedInUser` → /api/me, /api/invite 처럼 자격 전에 부르는 곳
- 공개: 의존성 없음 → 상태 확인 경로
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


MEMBER_GROUP = "members"
LOCAL_USER = {"sub": "local-dev", "username": "local-dev", "cognito:groups": [MEMBER_GROUP]}


def is_member(claims: dict) -> bool:
    """초대 코드를 통과한 회원인가. Cognito는 그룹이 없으면 cognito:groups 클레임을 넣지 않는다."""
    return MEMBER_GROUP in (claims.get("cognito:groups") or [])


def require_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    if os.environ.get("AUTH_DISABLED") == "1":
        return LOCAL_USER
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요하다")
    return verify_token(authorization.split(" ", 1)[1])


def require_member(user: Annotated[dict, Depends(require_user)]) -> dict:
    if not is_member(user):
        raise HTTPException(
            status_code=403, detail={"code": "not_member", "message": "초대 코드가 필요하다"}
        )
    return user


# 라우트에서: def handler(user: CurrentUser): ...
LoggedInUser = Annotated[dict, Depends(require_user)]
CurrentUser = Annotated[dict, Depends(require_member)]
