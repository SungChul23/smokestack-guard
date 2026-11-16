"""에이전트 서버 최소 앱 (배포 길 확인용). D·E가 LangChain/LangGraph + Bedrock으로 이어서 개발한다.

계약: specs/a-platform/009-service-infra/contracts/app-runtime.md
- 포트 8000, 상태 확인 GET /health
- 모든 에이전트 경로는 /agent/ 아래 (ALB가 접두사를 떼지 않는다)
- 모델은 서버 안에서 돌리지 않고 Bedrock을 API로 호출한다 (서버 메모리 2GB)
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="tms dashboard agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("APP_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """ALB 상태 확인. LLM·DB를 부르지 않는다."""
    return {"status": "ok"}


@app.get("/agent/health")
def agent_health() -> dict:
    return {"status": "ok", "app": "agent", "version": os.environ.get("APP_VERSION", "local")}
