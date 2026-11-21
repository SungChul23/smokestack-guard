"""대화 상태·재시도 응답 저장소 단위 시험 (spec 319). DB가 필요 없다.

실제 PostgreSQL에서 서버 2대를 흉내 내는 시험은
test_conversation_store_pg.py(환경 변수가 있을 때만).
"""

import logging

import pytest
from conftest import make_data
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.agent import api, conversation_store
from app.agent.contract import ChatRequest, ChatResponse, Trace
from app.agent.conversation_store import (
    make_checkpointer,
    make_guarded_saver,
    make_response_store,
)
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import SiteResolver
from app.agent.rds_data import DataSourceUnavailable
from app.agent.response_store import (
    CLEANUP_SQL,
    GET_SQL,
    MemoryResponseStore,
    PostgresResponseStore,
)
from app.agent.service import AgentService
from app.main import app


def sample(request_id: str = "r1", note: str = "안내") -> ChatResponse:
    return ChatResponse(
        request_id=request_id,
        conversation_id="c1",
        status="REFUSED",
        notices=[note],
        trace=Trace(turn_type="MESSAGE", route="DATA", reason="X", model=None, elapsed_ms=3),
    )


# ── 선택 ─────────────────────────────────────────────────────────────
def test_default_is_memory_and_unknown_kind_is_rejected():
    assert isinstance(make_checkpointer({}), InMemorySaver)
    assert isinstance(make_response_store({}), MemoryResponseStore)
    with pytest.raises(ValueError, match="AGENT_CHECKPOINT"):
        make_checkpointer({"AGENT_CHECKPOINT": "redis"})


# ── 메모리 저장소 (예전 동작과 같다) ───────────────────────────────────
def test_memory_store_keeps_the_latest_entries_per_user():
    store = MemoryResponseStore(max_cached=2)
    store.put("u", "a", sample("a"))
    store.put("u", "b", sample("b"))
    store.put("u", "c", sample("c"))
    assert store.get("u", "a") is None  # 가장 오래된 것이 밀려났다
    assert store.get("u", "c").request_id == "c"
    assert store.get("other", "c") is None  # 다른 사용자의 같은 request_id는 별개


def test_service_uses_the_injected_store_and_does_not_rerun_a_retry(clock):
    class Counting(MemoryResponseStore):
        def __init__(self):
            super().__init__()
            self.gets = self.puts = 0

        def get(self, user_sub, request_id):
            self.gets += 1
            return super().get(user_sub, request_id)

        def put(self, user_sub, request_id, response):
            self.puts += 1
            super().put(user_sub, request_id, response)

    data = make_data()
    resolver = SiteResolver(sites_from(data))
    calls = []

    class CountingExtractor:
        def __init__(self, inner):
            self.inner = inner

        def extract(self, message, now, *, has_last):
            calls.append(message)
            return self.inner.extract(message, now, has_last=has_last)

    store = Counting()
    service = AgentService(
        CountingExtractor(RuleExtractor(resolver)),
        data,
        InMemorySaver(),
        clock,
        "rule-dev",
        responses=store,
    )
    request = ChatRequest(message="가나에너지 굴뚝 1 어제 NOx 평균", request_id="req-1")
    first = service.chat(request, "u")
    again = service.chat(request, "u")
    assert len(calls) == 1 and again == first
    assert (store.gets, store.puts) == (2, 1)
    service.chat(ChatRequest(message="가나에너지 굴뚝 1 어제 NOx 평균"), "u")  # request_id 없음
    assert store.puts == 1  # request_id가 없으면 저장하지 않는다


# ── RDS 저장소 (가짜 연결) ─────────────────────────────────────────────
class Row:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeConn:
    def __init__(self, row=None, fail=False):
        self.row, self.fail = row, fail
        self.calls: list[tuple[str, object]] = []

    def connect(self):
        return self

    def __enter__(self):
        if self.fail:
            raise ConnectionError("host=secret-host password=secret-token")
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return Row(self.row)


def test_postgres_store_reads_a_stored_response_from_dict_or_tuple_rows():
    stored = sample("r9", "저장된 답").model_dump(mode="json")
    for row in ({"response": stored}, (stored,)):  # 체크포인터 풀은 dict, 일반 연결은 튜플
        conn = FakeConn(row)
        got = PostgresResponseStore(conn.connect).get("u", "r9")
        assert got == sample("r9", "저장된 답")
        sql, params = conn.calls[-1]
        assert sql == GET_SQL and params == ("u", "r9", 10)  # 10분 안의 재시도만


def test_postgres_store_misses_cleanly():
    assert PostgresResponseStore(FakeConn(None).connect).get("u", "none") is None


def test_postgres_store_never_blocks_a_question_when_the_store_is_down(caplog):
    store = PostgresResponseStore(FakeConn(fail=True).connect)
    with caplog.at_level(logging.WARNING):
        assert store.get("u", "r") is None  # 읽기 실패 = 처음 보는 요청으로 처리
        store.put("u", "r", sample())  # 저장 실패 = 이미 만든 답을 버리지 않고 넘어감
    assert caplog.text.count("재시도 응답") == 2  # 읽기·저장 실패가 각각 경고로 남는다


def test_postgres_store_cleans_up_old_rows_every_n_puts():
    conn = FakeConn()
    store = PostgresResponseStore(conn.connect, cleanup_every=2, keep_hours=24)
    for i in range(4):
        store.put("u", f"r{i}", sample(f"r{i}"))
    cleanups = [c for c in conn.calls if c[0] == CLEANUP_SQL]
    assert len(cleanups) == 2 and cleanups[0][1] == (24,)


# ── 장애는 503 ────────────────────────────────────────────────────────
def unreachable_pool() -> ConnectionPool:
    pool = ConnectionPool(
        "host=127.0.0.1 port=1 dbname=x user=x connect_timeout=1",
        min_size=0,
        max_size=1,
        timeout=1,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    pool.open()
    return pool


def test_guarded_saver_turns_connection_failures_into_data_source_unavailable():
    pool = unreachable_pool()
    try:
        saver = make_guarded_saver(pool)
        with pytest.raises(DataSourceUnavailable):
            saver.get_tuple({"configurable": {"thread_id": "t"}})
        with pytest.raises(DataSourceUnavailable):
            saver.setup()
    finally:
        pool.close()


def test_response_store_setup_failure_is_reported_as_unavailable(monkeypatch):
    pool = unreachable_pool()
    monkeypatch.setattr(conversation_store, "_write_pool", lambda: pool)
    try:
        with pytest.raises(DataSourceUnavailable):
            make_response_store({"AGENT_CHECKPOINT": "postgres"})
    finally:
        pool.close()


def test_a_dead_checkpoint_store_during_a_chat_is_a_503(monkeypatch, clock):
    pool = unreachable_pool()
    data = make_data()
    resolver = SiteResolver(sites_from(data))
    api.set_service(
        AgentService(
            RuleExtractor(resolver), data, make_guarded_saver(pool), clock, "rule-dev", resolver
        )
    )
    monkeypatch.setenv("AUTH_DISABLED", "1")
    try:
        response = TestClient(app).post(
            "/agent/chat", json={"message": "가나에너지 굴뚝 1 어제 NOx 평균 알려줘"}
        )
    finally:
        api.set_service(None)
        pool.close()
    assert response.status_code == 503
    assert "다시 시도" in response.json()["detail"]
    assert "127.0.0.1" not in response.text  # 접속 정보가 응답에 없다
