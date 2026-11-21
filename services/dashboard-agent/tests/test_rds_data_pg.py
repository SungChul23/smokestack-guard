"""RDS 데이터 소스를 실제 PostgreSQL에서 InMemory와 맞춰 본다 (spec 316).

A의 마이그레이션(services/dashboard-load/migrations/001~)을 올리고,
기준 데이터(conftest.make_data)를 A와 같은 형식(상태 행 value = null,
사업장 코드가 없는 굴뚝 포함)으로 심은 뒤, **실제 `tms_app` 역할**로 읽는다.
그래서 A가 준 권한(GRANT)으로 우리 쿼리가 되는지, 쓰기가 막히는지도 함께 확인한다.

환경 변수가 없으면 건너뛴다(A의 시험과 같은 방식).
    TEST_PG_PASSWORD(필수) TEST_PG_HOST(localhost) TEST_PG_PORT(55432) TEST_PG_USER(postgres)
    TMS_MIGRATIONS_DIR(기본: 저장소의 services/dashboard-load/migrations)
    로컬: docker run -d --name tms-pg-test -e POSTGRES_PASSWORD=test -p 55432:5432 \\
          pgvector/pgvector:pg16
"""

import os
import uuid
from datetime import timedelta
from pathlib import Path

import psycopg
import pytest
from conftest import AS_OF, DAY, make_data

from app.agent.rds_connect import SESSION_OPTIONS
from app.agent.rds_data import DataSourceUnavailable, RdsDataSource
from app.agent.tools import OK

MIGRATIONS = Path(
    os.environ.get("TMS_MIGRATIONS_DIR")
    or Path(__file__).resolve().parents[3] / "services" / "dashboard-load" / "migrations"
)
APP_PASSWORD = "tms-app-test-only"  # 일회용 로컬 컨테이너 안에서만 쓰는 시험용 값
UNMAPPED_KEY = "경기도|미연결사업장|1"  # 이름 이력에 없는 굴뚝(적재가 처음 본 키)


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


def _rds_key(stack) -> str:
    return f"{stack.region}|{stack.business}|{stack.code}"


def _seed(conn) -> None:
    data = make_data()
    sites: dict[str, object] = {}
    for stack in data.list_stacks():
        sites.setdefault(stack.site_id, stack)
    for site_id, stack in sites.items():
        conn.execute(
            "INSERT INTO ref.site"
            " (site_id, display_name, region_sido, region_sigungu, source_version)"
            " VALUES (%s, %s, %s, %s, 'test')",
            (site_id, stack.business, stack.region, stack.sigungu or None),
        )
        conn.execute(
            "INSERT INTO ref.site_name_map"
            " (area_nm, fact_manage_nm, valid_from, site_id, confirmed_by)"
            " VALUES (%s, %s, '2026-01-01', %s, 'auto')",
            (stack.region, stack.business, site_id),
        )
    for stack in data.list_stacks():
        conn.execute(
            "INSERT INTO ref.stack (stack_key, area_nm, fact_manage_nm, stack_code, source)"
            " VALUES (%s, %s, %s, %s, 'site_list')",
            (_rds_key(stack), stack.region, stack.business, stack.code),
        )
    conn.execute(
        "INSERT INTO ref.stack (stack_key, area_nm, fact_manage_nm, stack_code, source)"
        " VALUES (%s, '경기도', '미연결사업장', '1', 'observed')",
        (UNMAPPED_KEY,),
    )
    rows = []
    for (agent_key, item), observations in data._rows.items():  # noqa: SLF001  시험용 기준 데이터
        rds_key = _rds_key(data.get_stack(agent_key))
        for o in observations:
            value = o.value if o.status_code == OK else None  # A와 같다: 상태 행은 null
            ratio = None if value is None or not o.limit else value / o.limit * 100
            rows.append(
                (
                    rds_key,
                    item,
                    o.measured_at.replace(tzinfo=None),
                    value,
                    o.limit,
                    ratio,
                    o.status_code,
                )
            )
    rows.append((UNMAPPED_KEY, "nox", DAY.replace(tzinfo=None), 1.0, 100.0, 1.0, 0))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO obs.measurement_30m"
            " (stack_key, item, measured_at, value, limit_value, ratio_pct,"
            " status_code, load_path, loaded_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 'recent', now())",
            rows,
        )


@pytest.fixture(scope="module")
def pg_db():
    params = _params()
    admin = psycopg.connect(**params, dbname="postgres", autocommit=True)
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin.execute(f"CREATE DATABASE {name}")
    conn = psycopg.connect(**params, dbname=name, autocommit=True)
    try:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
        conn.execute(f"ALTER ROLE tms_app PASSWORD '{APP_PASSWORD}'")
        _seed(conn)
        yield {**params, "dbname": name}
    finally:
        conn.close()
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()


def _app_connection(pg_db, **extra):
    return psycopg.connect(
        host=pg_db["host"],
        port=pg_db["port"],
        dbname=pg_db["dbname"],
        user="tms_app",
        password=APP_PASSWORD,
        autocommit=True,
        **extra,
    )


@pytest.fixture
def rds(pg_db) -> RdsDataSource:
    return RdsDataSource(lambda: _app_connection(pg_db, options=SESSION_OPTIONS))


@pytest.fixture
def memory():
    return make_data()


def _comparable(rows):
    """상태 행의 value는 RDS에서 null, 기준 데이터에서는 0.0이다.
    그 차이만 지우고 나머지는 그대로 비교한다."""
    return [
        (r.measured_at, r.value if r.status_code == OK else None, r.limit, r.status_code)
        for r in rows
    ]


def test_stack_list_matches_memory_and_excludes_unmapped(rds, memory):
    mine = {
        (s.stack_key, s.site_id, s.business, s.code, s.region, s.sigungu) for s in rds.list_stacks()
    }
    expected = {
        (s.stack_key, s.site_id, s.business, s.code, s.region, s.sigungu)
        for s in memory.list_stacks()
    }
    assert mine == expected  # 미연결 굴뚝은 없고, 목록은 기준 데이터와 같다
    assert all("미연결" not in s.business for s in rds.list_stacks())


def test_find_and_get_match_memory(rds, memory):
    assert [s.stack_key for s in rds.find_stacks("동서식품", None)] == [
        s.stack_key for s in memory.find_stacks("동서식품", None)
    ]  # 이름이 같은 두 사업장
    assert len(rds.find_stacks("동서식품", None)) == 2
    assert [s.stack_key for s in rds.find_stacks("가나에너지", "2")] == ["100:2"]
    assert rds.get_stack("100:1") == memory.get_stack("100:1")
    assert rds.get_stack("999:9") is None


def test_every_stack_and_item_matches_memory_over_the_whole_day(rds, memory):
    start, end = DAY, DAY + timedelta(days=1)
    checked = 0
    for stack in memory.list_stacks():
        for item in ("nox", "sox"):
            want = memory.observations(stack.stack_key, item, start, end)
            got = rds.observations(stack.stack_key, item, start, end)
            assert _comparable(got) == _comparable(want), (stack.stack_key, item)
            checked += len(want)
    assert checked > 200  # 비어 있는 비교가 아니다


def test_missing_slot_stays_missing_and_status_rows_keep_null(rds):
    rows = rds.observations("100:1", "nox", DAY, DAY + timedelta(days=1))
    times = {r.measured_at for r in rows}
    assert DAY + timedelta(minutes=30 * 10) not in times  # 10번 칸은 행 자체가 없다
    status = {r.status_code: r for r in rows if r.status_code != OK}
    assert status[3].value is None and status[4].value is None  # 값을 0으로 채우지 않는다
    assert [r.status_code for r in rows if r.status_code == 3] == [3, 3]


def test_range_is_half_open_and_ordered(rds):
    start = DAY + timedelta(minutes=30 * 5)
    end = DAY + timedelta(minutes=30 * 8)
    rows = rds.observations("100:2", "nox", start, end)
    assert [r.measured_at for r in rows] == [start + timedelta(minutes=30 * i) for i in range(3)]


def test_as_of_is_the_latest_measurement_time(rds):
    assert rds.as_of() == AS_OF


def test_unmapped_stack_observations_are_not_reachable(rds):
    assert rds.observations(UNMAPPED_KEY, "nox", DAY, DAY + timedelta(days=1)) == []


def _service(data):
    from datetime import datetime

    from conftest import Clock
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agent.extractor import RuleExtractor
    from app.agent.graph import sites_from
    from app.agent.names import SiteResolver
    from app.agent.service import AgentService
    from app.agent.slots import KST

    clock = Clock(datetime(2026, 11, 11, 9, 0, tzinfo=KST))
    extractor = RuleExtractor(SiteResolver(sites_from(data)))
    return AgentService(extractor, data, InMemorySaver(), clock, "rule-dev")


def _normalized(response) -> dict:
    """요청마다 새로 만들어지는 값(요청 id, 소요 시간, 카드 id)만 빼고 응답 전체를 비교한다."""
    body = response.model_dump()
    body.pop("request_id")
    body.pop("trace")
    if body["card"]:
        body["card"].pop("card_id")
    return body


QUESTIONS = [
    "가나에너지 굴뚝 1 어제 NOx 평균 알려줘",  # 값 + 미수신·보수 중·누락 안내
    "가나에너지 굴뚝 2 어제 NOx 최대",
    "다라화학 굴뚝 3 어제 SOx 최대",  # 측정하지 않는 물질(기준값·측정값 없음)
    "동서식품 굴뚝 1 어제 NOx 평균",  # 이름이 같은 두 사업장 → 사업장 선택 카드
    "가나에너지 어제 NOx 평균",  # 굴뚝 선택 카드
    "없는이름의회사 어제 NOx 평균",
]


@pytest.mark.parametrize("message", QUESTIONS)
def test_whole_answers_are_the_same_for_memory_and_rds(rds, memory, message):
    from app.agent.contract import ChatRequest

    want = _service(memory).chat(ChatRequest(message=message, conversation_id="c1"), "u")
    got = _service(rds).chat(ChatRequest(message=message, conversation_id="c1"), "u")
    assert _normalized(got) == _normalized(want)
    assert want.status in {"ANSWERED", "NEEDS_INPUT", "REFUSED"}


def test_follow_up_answer_is_the_same_for_memory_and_rds(rds, memory):
    from app.agent.contract import ChatRequest

    answers = []
    for data in (memory, rds):
        service = _service(data)
        service.chat(
            ChatRequest(message="가나에너지 굴뚝 1 어제 NOx 평균 알려줘", conversation_id="c2"), "u"
        )
        answers.append(
            _normalized(service.chat(ChatRequest(message="그럼 SOx는?", conversation_id="c2"), "u"))
        )
    assert answers[0] == answers[1]


def test_the_rds_answer_carries_the_expected_number(rds):
    """같다는 것만이 아니라 값 자체도 확인한다(기준 데이터의 손계산: 1109 / 44)."""
    from app.agent.contract import ChatRequest

    response = _service(rds).chat(
        ChatRequest(message="가나에너지 굴뚝 1 어제 NOx 평균 알려줘", conversation_id="c3"), "u"
    )
    number = response.parts[0].numbers[0]
    assert number.value == pytest.approx(1109 / 44)
    assert (number.n_used, number.n_excluded, number.n_missing) == (44, 3, 1)
    assert response.data_as_of == "2026-11-10T23:30:00+09:00"


def test_app_role_can_read_but_cannot_write_the_data(pg_db):
    """A가 준 권한(GRANT) 자체를 확인한다. 세션 옵션 없이 연결해 권한만 본다."""
    with _app_connection(pg_db) as conn:
        assert conn.execute("SELECT count(*) FROM obs.measurement_30m").fetchone()[0] > 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM obs.measurement_30m")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE ref.site SET display_name = 'x'")


def test_session_options_make_even_allowed_writes_read_only(pg_db):
    """권한이 있는 쓰기(app 스키마)도 세션 옵션만으로 막힌다 = 권한과 별개의 두 번째 방어."""
    with _app_connection(pg_db) as conn:  # 옵션 없음: app 스키마에는 쓸 수 있다
        conn.execute("CREATE TABLE IF NOT EXISTS app.probe (x int)")
        conn.execute("INSERT INTO app.probe VALUES (1)")
    with _app_connection(pg_db, options=SESSION_OPTIONS) as conn:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("INSERT INTO app.probe VALUES (2)")


def test_connection_failure_is_reported_as_unavailable(pg_db):
    def bad():
        return psycopg.connect(
            host=pg_db["host"],
            port=pg_db["port"],
            dbname=pg_db["dbname"],
            user="tms_app",
            password="wrong",
            connect_timeout=3,
        )

    with pytest.raises(DataSourceUnavailable):
        RdsDataSource(bad).list_stacks()
