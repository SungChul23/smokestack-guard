"""요청·응답 계약 (specs/d-analytics/314-front-interpretation-decisions/contracts-draft.md 2절).

- 요청은 `message`와 `resume` 중 정확히 하나만 받는다(K1).
- 응답은 부분별 상태(`parts`), 구조화된 숫자(`numbers`), 카드(`card`)로 나눈다.
- 카드 문구와 선택지는 코드가 정한다. 모델이 쓴 문구를 내보내지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MESSAGE = (
    4000  # 전송 한도(이보다 길면 요청 자체를 거절). 질문 길이 제한(1,000자)과 안내는 guard가 한다
)

CardKind = Literal[
    "STACK_CANDIDATES",
    "STACK_CODE",
    "POLLUTANT",
    "TIME",
    "OPERATION",
    "CHOOSE_PART",
    "MAP_OR_RETYPE",
    "SCOPE",
    "PERIOD",
]
ChatStatus = Literal["ANSWERED", "NEEDS_INPUT", "PARTIAL", "REFUSED"]
PartStatus = Literal["DONE", "NEEDS_INPUT", "UNAVAILABLE", "SKIPPED"]
AgentName = Literal["data", "evidence", "prediction", "report", "ui", "system"]
TurnType = Literal["MESSAGE", "RESUME"]


class Context(BaseModel):
    """화면이 아는 것만 싣는다. 사용자 id는 싣지 않는다(서버가 토큰의 sub로 정한다)."""

    model_config = ConfigDict(extra="forbid")

    selectedStackId: str | None = Field(default=None, max_length=64)


class Resume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str = Field(min_length=1, max_length=64)
    option_id: str = Field(min_length=1, max_length=64)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = Field(default=None, max_length=64)
    request_id: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=MAX_MESSAGE)
    resume: Resume | None = None
    context: Context = Field(default_factory=Context)

    @model_validator(mode="after")
    def exactly_one_of_message_or_resume(self) -> ChatRequest:
        if self.message is not None:
            self.message = self.message.strip()
            if not self.message:
                raise ValueError("message는 비어 있을 수 없다")
        if (self.message is None) == (self.resume is None):
            raise ValueError("message와 resume 중 정확히 하나만 보내야 한다")
        return self


class Number(BaseModel):
    """출력 검증(숫자 대조)이 읽는 구조화된 값."""

    name: str
    pollutant: str
    value: float | None
    unit: str
    n_used: int
    n_excluded: int
    n_missing: int
    period: str
    as_of: str | None
    subject: str | None = None  # 순위 항목의 굴뚝 이름 등
    stack_key: str | None = None  # 순위 항목의 굴뚝 키(다음 조회가 이어받는다)
    rank: int | None = None


class Evidence(BaseModel):
    source: str
    article: str | None = None
    effective_date: str | None = None
    chunk_id: str | None = None
    url: str | None = None
    excerpt: str | None = None  # 조문 원문에서 그대로 가져온 해당 문장


class Part(BaseModel):
    part_id: str
    agent: AgentName
    status: PartStatus
    label: str
    answer: str | None = None
    numbers: list[Number] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    notice: str | None = None


class CardOption(BaseModel):
    id: str
    label: str
    skip_part: bool = False


class Card(BaseModel):
    card_id: str
    kind: CardKind
    message: str
    options: list[CardOption]


class Trace(BaseModel):
    turn_type: TurnType
    route: str = ""
    reason: str = ""
    model: str | None = None
    elapsed_ms: int = 0
    trace_id: str | None = None


class ChatResponse(BaseModel):
    request_id: str
    conversation_id: str
    status: ChatStatus
    data_as_of: str | None = None
    parts: list[Part] = Field(default_factory=list)
    card: Card | None = None
    notices: list[str] = Field(default_factory=list)
    trace: Trace
