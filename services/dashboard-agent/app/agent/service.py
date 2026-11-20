"""요청 하나를 처리한다: `message`면 새 질문, `resume`이면 카드 답.

같은 대화는 같은 thread로 잇는다.

- thread_id는 `<로그인 sub>:<conversation_id>`라 다른 사용자가 남의 대화를 이어갈 수 없다.
- 같은 `request_id`가 다시 오면(재시도) 저장해 둔 응답을 돌려주고 다시 실행하지 않는다.
- 만료되었거나 맞지 않는 `card_id`는 실행하지 않고 거절한다.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from langgraph.types import Command

from app.agent.contract import (
    Card,
    ChatRequest,
    ChatResponse,
    ChatStatus,
    Part,
    Trace,
)
from app.agent.graph import build_graph
from app.agent.guard import mask_pii
from app.agent.response_store import MemoryResponseStore, ResponseStore
from app.agent.slots import KST

Clock = Callable[[], datetime]


def _now_kst() -> datetime:
    return datetime.now(KST)


class AgentService:
    def __init__(
        self,
        extractor: Any,
        data: Any,
        checkpointer: Any,
        clock: Clock = _now_kst,
        model_name: str | None = None,
        resolver: Any = None,
        planner: Any = None,
        evidence: Any = None,
        responses: ResponseStore | None = None,
    ) -> None:
        self.graph = build_graph(extractor, data, checkpointer, resolver, planner, evidence)
        self.clock = clock
        self.model_name = model_name
        # 재시도 응답 저장소. 서버가 여러 대면 RDS 구현을 넣는다(기본은 이 프로세스 메모리).
        self.responses: ResponseStore = responses or MemoryResponseStore()

    # ── 입구 ──────────────────────────────────────────────────────────
    def chat(self, request: ChatRequest, user_sub: str) -> ChatResponse:
        started = time.perf_counter()
        # 같은 사용자의 같은 request_id는 재시도로 보고 저장된 응답을 돌려준다.
        if request.request_id:
            cached = self.responses.get(user_sub, request.request_id)
            if cached is not None:
                return cached
        conversation_id = request.conversation_id or uuid.uuid4().hex[:16]
        thread = f"{user_sub}:{conversation_id}"
        request_id = request.request_id or uuid.uuid4().hex[:16]
        config = {"configurable": {"thread_id": thread}}
        turn = "RESUME" if request.resume else "MESSAGE"
        if request.resume:
            response = self._resume(request, config, conversation_id, request_id, started)
        else:
            response = self._message(request, config, conversation_id, request_id, started)
        response = response.model_copy(
            update={"trace": response.trace.model_copy(update={"turn_type": turn})}
        )
        if request.request_id:
            self.responses.put(user_sub, request.request_id, response)
        return response

    # ── 새 질문 ───────────────────────────────────────────────────────
    def _message(self, request, config, conversation_id, request_id, started) -> ChatResponse:
        now = self.clock()
        result = self.graph.invoke(
            {
                "message": mask_pii(
                    request.message
                ),  # 개인정보는 그래프·체크포인트에 닿기 전에 가린다
                "now": now.isoformat(),
                "context": request.context.model_dump(),
            },
            config,
        )
        return self._response(result, config, conversation_id, request_id, started)

    # ── 카드 답 ───────────────────────────────────────────────────────
    def _resume(self, request, config, conversation_id, request_id, started) -> ChatResponse:
        pending = self._pending_card(config)
        resume = request.resume
        if pending is None or pending["card_id"] != resume.card_id:
            return self._refused(
                "이 카드는 만료되었습니다. 질문을 다시 입력해 주세요.",
                conversation_id,
                request_id,
                started,
                reason="CARD_EXPIRED",
            )
        if resume.option_id not in {o["id"] for o in pending["options"]}:
            return self._refused(
                "선택지에 없는 답입니다.", conversation_id, request_id, started, "BAD_OPTION"
            )
        result = self.graph.invoke(
            Command(resume={"card_id": resume.card_id, "option_id": resume.option_id}), config
        )
        return self._response(result, config, conversation_id, request_id, started)

    def _pending_card(self, config) -> dict | None:
        state = self.graph.get_state(config)
        for task in state.tasks:
            for interrupt in task.interrupts:
                value = interrupt.value
                if isinstance(value, dict) and "card" in value:
                    return value["card"]
        return None

    # ── 응답 만들기 ───────────────────────────────────────────────────
    def _response(self, result, config, conversation_id, request_id, started) -> ChatResponse:
        elapsed = int((time.perf_counter() - started) * 1000)
        pending = self._pending_card(config)
        if pending is not None:
            return ChatResponse(
                request_id=request_id,
                conversation_id=conversation_id,
                status="NEEDS_INPUT",
                data_as_of=None,
                parts=[],
                card=Card(**pending),
                notices=[],
                trace=Trace(
                    turn_type="MESSAGE",
                    route="DATA",
                    reason="NEEDS_INPUT",
                    model=self.model_name,
                    elapsed_ms=elapsed,
                ),
            )
        parts = [Part(**p) for p in result.get("parts") or []]
        done = [p for p in parts if p.status == "DONE"]
        status: ChatStatus
        if done and len(done) == len(parts):
            status = "ANSWERED"
        elif done:
            status = "PARTIAL"
        else:
            status = "REFUSED"
        return ChatResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            status=status,
            data_as_of=result.get("data_as_of"),
            parts=parts,
            card=None,
            notices=list(result.get("notices") or []),
            trace=Trace(
                turn_type="MESSAGE",
                route=result.get("route", ""),
                reason=result.get("reason", ""),
                model=self.model_name,
                elapsed_ms=elapsed,
            ),
        )

    def _refused(self, notice, conversation_id, request_id, started, reason) -> ChatResponse:
        return ChatResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            status="REFUSED",
            notices=[notice],
            trace=Trace(
                turn_type="RESUME",
                route="CARD",
                reason=reason,
                model=self.model_name,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            ),
        )
