"""대화 상태(체크포인트)와 재시도 응답을 RDS `app` 스키마에 저장한다 (spec 319).

서버가 2대 이상이거나 재시작해도 카드 대기 상태와 재시도가 이어지게 한다.
- AGENT_CHECKPOINT=postgres : LangGraph 체크포인트 표를 `app` 스키마에 만들어 쓴다.
  그 밖(기본 memory)은 메모리.
- 접속은 쓰기 풀(rds_connect.make_pool(read_only=False, search_path="app")) 하나를
  체크포인터와 재시도 응답 저장소가 함께 쓴다. 계정은 `tms_app`이다.
  `obs`·`ref`는 읽기만 되고 `app` 스키마에는 쓸 수 있다(A의 권한 설정).
- DB 장애는 `DataSourceUnavailable`로 바꿔 API가 503으로 응답하게 한다.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from functools import lru_cache

from app.agent.rds_data import DataSourceUnavailable
from app.agent.response_store import MemoryResponseStore, PostgresResponseStore, ResponseStore

log = logging.getLogger(__name__)
MESSAGE = "대화 상태를 저장소에서 다루지 못했다"


def _store_errors() -> tuple[type[BaseException], ...]:
    import psycopg
    import psycopg_pool

    return (psycopg.Error, psycopg_pool.PoolTimeout)


@lru_cache(maxsize=1)
def _write_pool():
    """쓰기 풀은 프로세스에서 하나만 만든다(서비스 조립이 실패해 다시 시도돼도 늘지 않는다)."""
    from psycopg.rows import dict_row

    from app.agent.rds_connect import make_pool

    return make_pool(
        read_only=False,
        search_path="app",
        # PostgresSaver가 요구하는 연결 설정
        extra_kwargs={"prepare_threshold": 0, "row_factory": dict_row},
        name="agent-state",
    )


def make_guarded_saver(pool):
    """DB 오류를 DataSourceUnavailable로 바꾸는 PostgresSaver를 만든다."""
    from langgraph.checkpoint.postgres import PostgresSaver

    errors = _store_errors()

    class GuardedPostgresSaver(PostgresSaver):
        def setup(self):
            try:
                return super().setup()
            except errors as error:
                raise DataSourceUnavailable(MESSAGE) from error

        def get_tuple(self, config):
            try:
                return super().get_tuple(config)
            except errors as error:
                raise DataSourceUnavailable(MESSAGE) from error

        def put(self, config, checkpoint, metadata, new_versions):
            try:
                return super().put(config, checkpoint, metadata, new_versions)
            except errors as error:
                raise DataSourceUnavailable(MESSAGE) from error

        def put_writes(self, config, writes, task_id, task_path=""):
            try:
                return super().put_writes(config, writes, task_id, task_path)
            except errors as error:
                raise DataSourceUnavailable(MESSAGE) from error

        def list(self, config, *, filter=None, before=None, limit=None):  # noqa: A002
            try:
                yield from super().list(config, filter=filter, before=before, limit=limit)
            except errors as error:
                raise DataSourceUnavailable(MESSAGE) from error

        def delete_thread(self, thread_id):
            try:
                return super().delete_thread(thread_id)
            except errors as error:
                raise DataSourceUnavailable(MESSAGE) from error

    return GuardedPostgresSaver(pool)


def _kind(env: Mapping[str, str]) -> str:
    kind = env.get("AGENT_CHECKPOINT", "memory")
    if kind not in ("memory", "postgres"):
        raise ValueError(f"알 수 없는 AGENT_CHECKPOINT: {kind}")
    return kind


def make_checkpointer(env: Mapping[str, str] | None = None):
    """체크포인터를 환경 변수로 고른다. postgres면 표를 만들고(이미 있으면 그대로) 돌려준다."""
    env = os.environ if env is None else env
    if _kind(env) == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()
    saver = make_guarded_saver(_write_pool())
    saver.setup()
    return saver


def make_response_store(env: Mapping[str, str] | None = None) -> ResponseStore:
    env = os.environ if env is None else env
    if _kind(env) == "memory":
        return MemoryResponseStore()
    store = PostgresResponseStore(_write_pool().connection)
    try:
        store.setup()
    except _store_errors() as error:
        raise DataSourceUnavailable(MESSAGE) from error
    return store
