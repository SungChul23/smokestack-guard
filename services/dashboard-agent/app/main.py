"""에이전트 서버 최소 앱 (배포 길 확인용). D·E가 LangChain/LangGraph + Bedrock으로 이어서 개발한다.

계약: specs/a-platform/009-service-infra/contracts/app-runtime.md
- 포트 8000, 상태 확인 GET /health
- 모든 에이전트 경로는 /agent/ 아래 (ALB가 접두사를 떼지 않는다)
- 모델은 서버 안에서 돌리지 않고 Bedrock을 API로 호출한다 (서버 메모리 2GB)
- 로그인 필수: 운영 확인용(/health, /agent/health)만 공개.
  새 라우트는 인자에 `user: CurrentUser`를 붙인다 (app/auth.py)
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import CurrentUser

app = FastAPI(title="tms dashboard agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("APP_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health() -> dict:
    """ALB 상태 확인. LLM·DB를 부르지 않는다."""
    return {"status": "ok"}


@app.get("/agent/health")
def agent_health() -> dict:
    return {"status": "ok", "app": "agent", "version": os.environ.get("APP_VERSION", "local")}


@app.get("/agent/me")
def me(user: CurrentUser) -> dict:
    """로그인 확인용."""
    return {"sub": user.get("sub"), "username": user.get("username")}
