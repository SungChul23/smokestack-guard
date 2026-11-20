"""POST /agent/chat. 로그인 필수이고, 사용자 id는 토큰의 sub에서만 얻는다."""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

from app.agent.contract import ChatRequest, ChatResponse
from app.agent.data import InMemoryDataSource, JsonDayDataSource
from app.agent.evidence import default_agent
from app.agent.extractor import BedrockExtractor, RuleExtractor
from app.agent.graph import sites_from
from app.agent.hybrid import HybridExtractor
from app.agent.names import SiteResolver
from app.agent.planner import BedrockPlanner
from app.agent.service import AgentService
from app.agent.slots import KST
from app.agent.summarizer import GroundedSummarizer
from app.auth import CurrentUser

router = APIRouter()

_service: AgentService | None = None


def set_service(service: AgentService | None) -> None:
    """시험이나 다른 구성에서 서비스를 바꿔 끼운다."""
    global _service
    _service = service


def _llm(resolver: SiteResolver) -> tuple[object, object | None, str, object | None]:
    """해석기·계획기를 환경 변수로 고른다.

    AGENT_LLM_BACKEND: none(정규식만, 기본) | bedrock |
        local-agent(개발용: 로컬 에이전트가 파일로 요청을 받아 답함)
    AGENT_LOCAL_AGENT_DIR: local-agent의 요청·답 폴더
    AGENT_BEDROCK_MODEL: bedrock 모델/추론 프로필 ID (AWS_REGION 기본 ap-northeast-2)
    """
    rule = RuleExtractor(resolver)
    backend = os.environ.get("AGENT_LLM_BACKEND", "none")
    if backend == "none":
        return rule, None, "rule-dev", None
    if backend == "local-agent":
        from app.agent.local_agent import LocalAgentClient

        client = LocalAgentClient(Path(os.environ["AGENT_LOCAL_AGENT_DIR"]))
        model = "local-agent"
    elif backend == "bedrock":
        import boto3

        client = boto3.client(
            "bedrock-runtime", region_name=os.environ.get("AWS_REGION", "ap-northeast-2")
        )
        model = os.environ["AGENT_BEDROCK_MODEL"]
    else:
        raise ValueError(f"알 수 없는 AGENT_LLM_BACKEND: {backend}")
    extractor = HybridExtractor(rule, BedrockExtractor(client, model))
    return extractor, BedrockPlanner(client, model), model, GroundedSummarizer(client, model)


@lru_cache(maxsize=1)
def _default_service() -> AgentService:
    """환경 변수로 구성한다. 운영 데이터(RDS)는 아직 연결하지 않았다.

    AGENT_LOCAL_DAY_DIR: 하루치 정적 자료 폴더(개발용). 없으면 빈 데이터로 뜬다.
    AGENT_FIXED_NOW: 'YYYY-MM-DDTHH:MM' (KST). 보관 자료로 시험할 때 현재 시각을 고정한다.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    day_dir = os.environ.get("AGENT_LOCAL_DAY_DIR")
    data = JsonDayDataSource(Path(day_dir)) if day_dir else InMemoryDataSource([], {})
    resolver = SiteResolver(sites_from(data))
    fixed = os.environ.get("AGENT_FIXED_NOW")
    clock = (
        (lambda: datetime.fromisoformat(fixed).replace(tzinfo=KST))
        if fixed
        else (lambda: datetime.now(KST))
    )
    extractor, planner, model, summarizer = _llm(resolver)
    return AgentService(
        extractor,
        data,
        InMemorySaver(),
        clock,
        model,
        resolver,
        planner,
        default_agent(summarizer),
    )


@router.post("/agent/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: CurrentUser) -> ChatResponse:
    service = _service or _default_service()
    return service.chat(request, user_sub=str(user["sub"]))
