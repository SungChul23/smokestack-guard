"""같은 `request_id` 재시도에 돌려줄 응답 저장소 (spec 319).

클라이언트가 응답을 못 받고 같은 `request_id`로 다시 보내면, 다시 실행하지 않고
저장한 응답을 돌려준다. 다시 실행하면 카드 선택은 첫 호출이 이미 카드를 소비해
"카드가 만료되었습니다"라는 거짓 오류가 난다.

- MemoryResponseStore: 서버 프로세스 안(기본). 서버가 1대일 때만 맞다.
- PostgresResponseStore: RDS `app.chat_response`.
  서버가 2대 이상이거나 재시작해도 재시도가 이어진다.
  저장은 최선 노력이다: 저장소가 닫혀 있어도 사용자의 질문 자체는 막지 않고, 경고 로그만 남긴다.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol

from app.agent.contract import ChatResponse

MAX_CACHED = 500
log = logging.getLogger(__name__)


class ResponseStore(Protocol):
    def get(self, user_sub: str, request_id: str) -> ChatResponse | None: ...

    def put(self, user_sub: str, request_id: str, response: ChatResponse) -> None: ...


class MemoryResponseStore:
    def __init__(self, max_cached: int = MAX_CACHED) -> None:
        self._done: OrderedDict[tuple[str, str], ChatResponse] = OrderedDict()
        self._max = max_cached

    def get(self, user_sub: str, request_id: str) -> ChatResponse | None:
        return self._done.get((user_sub, request_id))

    def put(self, user_sub: str, request_id: str, response: ChatResponse) -> None:
        self._done[(user_sub, request_id)] = response
        while len(self._done) > self._max:
            self._done.popitem(last=False)


CREATE_SQL = (
    """
    CREATE TABLE IF NOT EXISTS app.chat_response (
      user_sub   text NOT NULL,
      request_id text NOT NULL,
      response   jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_sub, request_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS chat_response_created ON app.chat_response (created_at)",
)
GET_SQL = (
    "SELECT response FROM app.chat_response"
    " WHERE user_sub = %s AND request_id = %s"
    " AND created_at > now() - make_interval(mins => %s)"
)
PUT_SQL = (
    "INSERT INTO app.chat_response (user_sub, request_id, response) VALUES (%s, %s, %s)"
    " ON CONFLICT (user_sub, request_id) DO NOTHING"
)
CLEANUP_SQL = "DELETE FROM app.chat_response WHERE created_at < now() - make_interval(hours => %s)"


def _first(row: Any) -> Any:
    """행이 튜플이든 dict(체크포인터 풀의 row_factory)든 첫 값을 꺼낸다."""
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


class PostgresResponseStore:
    def __init__(
        self,
        connect: Callable[[], AbstractContextManager[Any]],
        *,
        window_minutes: int = 10,
        keep_hours: int = 24,
        cleanup_every: int = 50,
    ) -> None:
        self._connect = connect
        self._window = window_minutes
        self._keep = keep_hours
        self._every = cleanup_every
        self._puts = 0

    def setup(self) -> None:
        """표를 만든다(이미 있으면 그대로). 실패하면 호출한 쪽이 처리한다."""
        with self._connect() as conn:
            for sql in CREATE_SQL:
                conn.execute(sql)

    def get(self, user_sub: str, request_id: str) -> ChatResponse | None:
        try:
            with self._connect() as conn:
                row = conn.execute(GET_SQL, (user_sub, request_id, self._window)).fetchone()
            return None if row is None else ChatResponse.model_validate(_first(row))
        except Exception as error:  # noqa: BLE001  저장소 문제로 질문을 막지 않는다
            log.warning("재시도 응답을 읽지 못했다: %r", error)
            return None

    def put(self, user_sub: str, request_id: str, response: ChatResponse) -> None:
        from psycopg.types.json import Jsonb

        try:
            with self._connect() as conn:
                conn.execute(
                    PUT_SQL, (user_sub, request_id, Jsonb(response.model_dump(mode="json")))
                )
                self._puts += 1
                if self._puts % self._every == 0:
                    conn.execute(CLEANUP_SQL, (self._keep,))
        except Exception as error:  # noqa: BLE001  저장소 문제로 이미 만든 답을 버리지 않는다
            log.warning("재시도 응답을 저장하지 못했다: %r", error)
