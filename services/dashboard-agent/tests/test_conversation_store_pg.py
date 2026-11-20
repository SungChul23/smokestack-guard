"""서버 2대를 흉내 내 대화 상태·재시도 응답이 RDS로 이어지는지 실제 PostgreSQL에서 확인한다.

spec 319.

A의 마이그레이션을 올리고 **실제 `tms_app` 역할**(`app` 스키마에만 쓸 수 있다)로 접속한다.
"서버"는 각자 새 접속 풀·체크포인터·재시도 저장소·AgentService를 가진 독립된 인스턴스다.

환경 변수가 없으면 건너뛴다(test_rds_data_pg.py와 같다).
    TEST_PG_PASSWORD(필수) TEST_PG_HOST(localhost) TEST_PG_PORT(55432) TEST_PG_USER(postgres)
    TMS_MIGRATIONS_DIR(기본: 저장소의 services/dashboard-load/migrations)
"""

import os
import uuid
from pathlib import Path

import psycopg
import pytest
from conftest import make_data
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.agent.contract import ChatRequest
from app.agent.conversation_store import make_guarded_saver
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import SiteResolver
from app.agent.rds_connect import WRITE_SESSION_OPTIONS
from app.agent.response_store import MemoryResponseStore, PostgresResponseStore
from app.agent.service import AgentService

MIGRATIONS = Path(
    os.environ.get("TMS_MIGRATIONS_DIR")
    or Path(__file__).resolve().parents[3] / "services" / "dashboard-load" / "migrations"
)
APP_PASSWORD = "tms-app-test-only"  # 일회용 로컬 컨테이너 안에서만 쓰는 시험용 값
USER = "user-a"


def _params() -> dict:
    password = os.environ.get("TEST_PG_PASSWORD")
    if not password:
        pytest.skip("TEST_PG_PASSWORD가 없어 DB 시험을 건너뛴다")
    if not MIGRATIONS.is_dir():
        pytest.skip(f"마이그레이션 폴더가 없다: {MIGRATIONS}")
    return {
        "host": os.environ.get("TEST_PG_HOST", "localhost"),
        "port": int(os.environ.get("TEST_PG_PORT", "55432")),
        "user": os.environ.get("TEST_PG_USER", "postgres"),
        "password": password,
    }


@pytest.fixture(scope="module")
def state_db():
    params = _params()
    admin = psycopg.connect(**params, dbname="postgres", autocommit=True)
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin.execute(f"CREATE DATABASE {name}")
    conn = psycopg.connect(**params, dbname=name, autocommit=True)
    try:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
        conn.execute(f"ALTER ROLE tms_app PASSWORD '{APP_PASSWORD}'")
        yield {**params, "dbname": name}
    finally:
        conn.close()
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()


def _pool(state_db) -> ConnectionPool:
    """make_pool(read_only=False, search_path="app")와 같은 설정(IAM 대신 시험용 비밀번호)."""
    pool = ConnectionPool(
        conninfo="",
        kwargs={
            "host": state_db["host"],
            "port": state_db["port"],
            "dbname": state_db["dbname"],
            "user": "tms_app",
            "password": APP_PASSWORD,
            "options": WRITE_SESSION_OPTIONS + " -c search_path=app",
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        min_size=1,
        max_size=4,
        timeout=10,
        check=ConnectionPool.check_connection,
        open=True,
    )
    return pool


class Server:
    """독립된 서버 한 대."""

    def __init__(self, state_db, clock, *, shared_store: bool = True):
        self.pool = _pool(state_db)
        self.saver = make_guarded_saver(self.pool)
        self.saver.setup()
        self.store = PostgresResponseStore(self.pool.connection)
        self.store.setup()
        data = make_data()
        resolver = SiteResolver(sites_from(data))
        self.calls: list[str] = []
        inner = RuleExtractor(resolver)
        calls = self.calls

        class Counting:
            def extract(self, message, now, *, has_last):
                calls.append(message)
                return inner.extract(message, now, has_last=has_last)

        self.service = AgentService(
            Counting(),
            data,
            self.saver,
            clock,
            "rule-dev",
            resolver,
            responses=self.store if shared_store else MemoryResponseStore(),
        )

    def ask(self, message, conversation_id=None, user=USER, request_id=None):
        return self.service.chat(
            ChatRequest(message=message, conversation_id=conversation_id, request_id=request_id),
            user,
        )

    def pick(self, response, option_id, user=USER, request_id=None):
        return self.service.chat(
            ChatRequest(
                conversation_id=response.conversation_id,
                request_id=request_id,
                resume={"card_id": response.card.card_id, "option_id": option_id},
            ),
            user,
        )

    def close(self):
        self.pool.close()


@pytest.fixture
def servers(state_db, clock):
    made: list[Server] = []

    def make(**kwargs) -> Server:
        server = Server(state_db, clock, **kwargs)
        made.append(server)
        return server

    yield make
    for server in made:
        server.close()


QUESTION = "가나에너지 어제 NOx 평균"  # 굴뚝이 둘이라 굴뚝 선택 카드가 뜬다


# ── 저장 위치 ─────────────────────────────────────────────────────────
def test_tables_live_in_the_app_schema_only_and_setup_is_repeatable(servers, state_db):
    first = servers()
    servers()  # 두 번째 서버가 뜨며 setup을 다시 실행해도 그대로다
    first.saver.setup()
    with psycopg.connect(
        host=state_db["host"],
        port=state_db["port"],
        dbname=state_db["dbname"],
        user=state_db["user"],
        password=state_db["password"],
    ) as conn:
        rows = conn.execute(
            "SELECT table_schema, table_name FROM information_schema.tables"
            " WHERE table_name IN ('checkpoints', 'checkpoint_blobs', 'checkpoint_writes',"
            " 'checkpoint_migrations', 'chat_response')"
        ).fetchall()
    assert {schema for schema, _ in rows} == {"app"}  # public 등 다른 스키마에는 없다
    assert {name for _, name in rows} == {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
        "chat_response",
    }


# ── 서버 2대 ──────────────────────────────────────────────────────────
def test_a_card_asked_on_one_server_is_answered_on_another(servers):
    one, two = servers(), servers()
    first = one.ask(QUESTION, "conv-1")
    assert first.status == "NEEDS_INPUT" and first.card.kind == "STACK_CODE"
    second = two.pick(first, "100:2")  # 다른 서버(별도 풀·체크포인터)에서 답한다
    assert second.status == "ANSWERED" and second.parts[0].numbers[0].value == 10


def test_the_card_survives_a_server_restart(servers):
    one = servers()
    first = one.ask(QUESTION, "conv-2")
    one.close()  # 서버가 내려간다(접속 풀이 닫힌다)
    restarted = servers()
    second = restarted.pick(first, "100:1")
    assert second.status == "ANSWERED"


def test_another_user_cannot_resume_somebody_elses_card(servers):
    one, two = servers(), servers()
    first = one.ask(QUESTION, "conv-3")
    other = two.pick(first, "100:2", user="user-b")
    assert other.status == "REFUSED" and "만료" in other.notices[0]


def test_follow_up_context_is_kept_across_servers(servers):
    one, two, solo = servers(), servers(), servers()
    one.ask("가나에너지 굴뚝 1 어제 NOx 평균 알려줘", "conv-4")
    across = two.ask("그럼 SOx는?", "conv-4")  # 마지막 질문의 사업장·굴뚝·시간을 이어받는다
    solo.ask("가나에너지 굴뚝 1 어제 NOx 평균 알려줘", "conv-4b")
    baseline = solo.ask("그럼 SOx는?", "conv-4b")  # 한 서버 안에서 이어간 답
    assert across.parts and across.status == baseline.status
    assert [p.model_dump() for p in across.parts] == [p.model_dump() for p in baseline.parts]


# ── 재시도 ────────────────────────────────────────────────────────────
def test_a_retried_card_choice_on_the_other_server_returns_the_same_answer(servers):
    one, two = servers(), servers()
    first = one.ask(QUESTION, "conv-5")
    answered = one.pick(first, "100:2", request_id="retry-1")
    again = two.pick(first, "100:2", request_id="retry-1")  # 응답을 못 받아 다른 서버로 재시도
    assert again.status == "ANSWERED" and "만료" not in " ".join(again.notices)
    assert again.parts[0].numbers == answered.parts[0].numbers
    assert again.request_id == answered.request_id


def test_without_the_shared_store_the_retry_would_look_expired(servers):
    """공유 저장소가 없을 때(예전 동작)는 같은 재시도가 거짓 '만료' 오류가 된다."""
    one, two = servers(), servers(shared_store=False)
    first = one.ask(QUESTION, "conv-6")
    one.pick(first, "100:2", request_id="retry-2")
    again = two.pick(first, "100:2", request_id="retry-2")
    assert again.status == "REFUSED" and "만료" in again.notices[0]


def test_a_retried_message_is_not_run_again_on_the_other_server(servers):
    one, two = servers(), servers()
    first = one.ask("가나에너지 굴뚝 1 어제 NOx 평균 알려줘", "conv-7", request_id="retry-3")
    again = two.ask("가나에너지 굴뚝 1 어제 NOx 평균 알려줘", "conv-7", request_id="retry-3")
    assert two.calls == []  # 다른 서버는 질문을 해석하지도 않았다
    assert again.parts[0].numbers == first.parts[0].numbers


def test_old_retry_responses_are_ignored_and_cleaned_up(servers):
    server = servers()
    server.ask("가나에너지 굴뚝 1 어제 NOx 평균 알려줘", "conv-8", request_id="old-1")
    with server.pool.connection() as conn:
        conn.execute(
            "UPDATE app.chat_response SET created_at = now() - interval '1 hour'"
            " WHERE request_id = 'old-1'"
        )
    assert server.store.get(USER, "old-1") is None  # 10분이 지난 재시도로는 보지 않는다
    with server.pool.connection() as conn:
        conn.execute(
            "UPDATE app.chat_response SET created_at = now() - interval '3 days'"
            " WHERE request_id = 'old-1'"
        )
    fresh = server.ask("가나에너지 굴뚝 1 어제 NOx 평균 알려줘", "conv-8", request_id="new-1")
    # 저장이 cleanup_every번 쌓이면 24시간 지난 행을 지운다. 여기서는 1번마다로 줄여 확인한다.
    PostgresResponseStore(server.pool.connection, cleanup_every=1).put(USER, "new-2", fresh)
    with server.pool.connection() as conn:
        rows = conn.execute("SELECT request_id FROM app.chat_response").fetchall()
    ids = {row["request_id"] for row in rows}
    assert "old-1" not in ids  # 3일 지난 행은 정리됐다
    assert {"new-1", "new-2"} <= ids  # 새 행은 남아 있다


# ── 연결이 끊겨도 ─────────────────────────────────────────────────────
def test_a_server_keeps_working_after_the_database_drops_its_connections(servers, state_db):
    """DB 점검·장애·Multi-AZ 전환(failover)으로 연결이 끊긴 상황.

    풀이 끊어진 연결을 버리고 새로 맺어야 한다."""
    server = servers()
    first = server.ask(QUESTION, "conv-9")
    admin = psycopg.connect(
        host=state_db["host"],
        port=state_db["port"],
        dbname="postgres",
        user=state_db["user"],
        password=state_db["password"],
        autocommit=True,
    )
    try:
        killed = admin.execute(
            "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity"
            " WHERE usename = 'tms_app' AND datname = %s",
            (state_db["dbname"],),
        ).fetchone()[0]
    finally:
        admin.close()
    assert killed >= 1  # 실제로 끊었다
    second = server.pick(first, "100:2")  # 끊긴 뒤의 첫 호출도 성공한다
    assert second.status == "ANSWERED" and second.parts[0].numbers[0].value == 10
