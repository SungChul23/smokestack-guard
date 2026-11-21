"""POST /agent/chat. 로그인 필수이고, 사용자 id는 토큰의 sub에서만 얻는다."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.agent.contract import ChatRequest, ChatResponse
from app.agent.data import InMemoryDataSource, JsonDayDataSource
from app.agent.evidence import default_agent
from app.agent.extractor import BedrockExtractor, RuleExtractor
from app.agent.graph import sites_from
from app.agent.hybrid import HybridExtractor
from app.agent.names import SiteResolver
from app.agent.planner import BedrockPlanner
from app.agent.rds_data import DataSourceUnavailable
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
def _rds_pool():
    """RDS 접속 풀은 프로세스에서 하나만 만든다.

    서비스 조립이 실패해 다시 시도되더라도 풀(과 배경 스레드)이 요청마다 늘어나지 않게 한다.
    """
    from app.agent.rds_connect import make_pool

    return make_pool()


def _data_source() -> object:
    """데이터 원본을 환경 변수로 고른다.

    AGENT_DATA_SOURCE=rds: RDS(`ref`·`obs`)를 읽는다. 접속은 rds_connect.py(DB_HOST 등, IAM 인증)
    그 밖: AGENT_LOCAL_DAY_DIR 이 있으면 하루치 정적 자료(개발용), 없으면 빈 데이터
    """
    if os.environ.get("AGENT_DATA_SOURCE") == "rds":
        from app.agent.rds_data import RdsDataSource

        return RdsDataSource(_rds_pool().connection)
    day_dir = os.environ.get("AGENT_LOCAL_DAY_DIR")
    return JsonDayDataSource(Path(day_dir)) if day_dir else InMemoryDataSource([], {})


@lru_cache(maxsize=1)
def _default_service() -> AgentService:
    """환경 변수로 구성한다.

    AGENT_DATA_SOURCE / AGENT_LOCAL_DAY_DIR: _data_source() 참고.
    AGENT_CHECKPOINT=postgres: 대화 상태와 재시도 응답을 RDS `app` 스키마에 둔다.
        서버가 2대 이상일 때 필요하다. 그 밖(기본 memory)은 이 프로세스 메모리.
        자세한 것은 conversation_store.py 참고.
    AGENT_FIXED_NOW: 'YYYY-MM-DDTHH:MM' (KST). 보관 자료로 시험할 때 현재 시각을 고정한다.
    """
    from app.agent.conversation_store import make_checkpointer, make_response_store

    data = _data_source()
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
        make_checkpointer(),
        clock,
        model,
        resolver,
        planner,
        default_agent(summarizer),
        make_response_store(),
    )


@router.post("/agent/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: CurrentUser) -> ChatResponse:
    try:
        # 서비스 조립도 안에서 한다: 조립 때 굴뚝 목록을 읽으므로 DB가 닫혀 있으면 여기서 실패한다.
        service = _service or _default_service()
        return service.chat(request, user_sub=str(user["sub"]))
    except DataSourceUnavailable as error:
        # 원인(접속 정보 등)은 응답에 싣지 않는다. 서버 로그에는 원인 체인이 남는다.
        logging.getLogger(__name__).error("데이터 원본을 읽지 못했다: %r", error.__cause__)
        raise HTTPException(
            status_code=503, detail="데이터를 읽지 못했습니다. 잠시 후 다시 시도해 주세요."
        ) from error
