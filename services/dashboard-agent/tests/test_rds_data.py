"""RDS 데이터 소스 단위 시험 (spec 316). 가짜 연결을 쓰므로 DB가 필요 없다.

실제 PostgreSQL과 맞춰 보는 시험은 test_rds_data_pg.py(환경 변수가 있을 때만).
"""

from datetime import datetime, timedelta

import pytest

from app.agent.rds_data import (
    AS_OF_SQL,
    DataSourceUnavailable,
    RdsDataSource,
)
from app.agent.slots import KST


class Result:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class FakeDb:
    """execute가 SQL 문구로 갈린다. 연결 자체가 컨텍스트 매니저다."""

    def __init__(self) -> None:
        self.stack_rows: list[tuple] = []
        self.obs_rows: list[tuple] = []
        self.max_at: datetime | None = None
        self.calls: list[tuple[str, object]] = []
        self.fail = False

    def connect(self) -> "FakeDb":
        return self

    def __enter__(self) -> "FakeDb":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> Result:
        self.calls.append((sql, params))
        if self.fail:
            raise ConnectionError("host=secret-host password=secret-token")
        if "ref.v_stack" in sql:
            return Result(self.stack_rows)
        if sql.strip() == AS_OF_SQL:
            return Result([(self.max_at,)])
        return Result(self.obs_rows)

    def count(self, needle: str) -> int:
        return sum(1 for sql, _ in self.calls if needle in sql)


class Tick:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def stack_row(key, site, code, name="㈜가나에너지", region="경기도", sigungu="성남시"):
    return (key, site, code, name, region, sigungu)


@pytest.fixture
def db() -> FakeDb:
    d = FakeDb()
    d.stack_rows = [
        stack_row("경기도|㈜가나에너지|2", "100", "2"),
        stack_row("경기도|㈜가나에너지|10", "100", "10"),
        stack_row("경기도|㈜가나에너지|1", "100", "1"),
        stack_row("울산광역시|다라화학(주)|3", "200", "3", "다라화학(주)", "울산광역시", None),
    ]
    return d


@pytest.fixture
def tick() -> Tick:
    return Tick()


@pytest.fixture
def source(db, tick) -> RdsDataSource:
    return RdsDataSource(db.connect, stack_ttl=3600, as_of_ttl=60, monotonic=tick)


def test_stacks_are_keyed_by_site_and_code_and_sorted_numerically(source):
    keys = [s.stack_key for s in source.list_stacks()]
    assert keys == ["100:1", "100:2", "100:10", "200:3"]  # 2 < 10 (글자순이 아니라 숫자순)
    info = source.get_stack("100:2")
    assert (info.site_id, info.business, info.code, info.region, info.sigungu) == (
        "100",
        "㈜가나에너지",
        "2",
        "경기도",
        "성남시",
    )
    assert source.get_stack("200:3").sigungu == ""  # null은 빈 문자열
    assert source.get_stack("999:1") is None


def test_find_stacks_matches_normalized_names_and_code(source):
    assert [s.stack_key for s in source.find_stacks("가나에너지", None)] == [
        "100:1",
        "100:2",
        "100:10",
    ]
    assert [s.stack_key for s in source.find_stacks("㈜가나에너지", "10")] == ["100:10"]
    assert source.find_stacks("없는사업장", None) == []


def test_stack_list_is_read_once_until_ttl(source, db, tick):
    source.list_stacks()
    source.find_stacks("가나에너지", None)
    source.get_stack("100:1")
    assert db.count("ref.v_stack") == 1
    tick.now += 3599
    source.list_stacks()
    assert db.count("ref.v_stack") == 1
    tick.now += 2  # TTL 지남
    source.list_stacks()
    assert db.count("ref.v_stack") == 2


def test_observations_convert_times_and_keep_null_values(source, db):
    start = datetime(2026, 11, 10, 0, 0, tzinfo=KST)
    end = start + timedelta(hours=1)
    db.obs_rows = [
        (datetime(2026, 11, 10, 0, 0), 12.5, 200.0, 0),
        (datetime(2026, 11, 10, 0, 30), None, 200.0, 3),  # 미수신: value null
    ]
    rows = source.observations("100:1", "nox", start, end)
    assert [(r.measured_at, r.value, r.limit, r.status_code) for r in rows] == [
        (datetime(2026, 11, 10, 0, 0, tzinfo=KST), 12.5, 200.0, 0),
        (datetime(2026, 11, 10, 0, 30, tzinfo=KST), None, 200.0, 3),
    ]
    sql, params = db.calls[-1]
    assert "obs.measurement_30m" in sql
    keys, item, low, high = params
    assert keys == ["경기도|㈜가나에너지|1"]
    assert item == "nox"
    assert (low, high) == (datetime(2026, 11, 10, 0, 0), datetime(2026, 11, 10, 1, 0))  # KST 벽시계


def test_observation_range_given_in_utc_is_converted_to_kst_wall_clock(source, db):
    from datetime import UTC

    start = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)  # = 11-10 00:00 KST
    source.observations("100:1", "sox", start, start + timedelta(hours=2))
    _, params = db.calls[-1]
    assert params[2] == datetime(2026, 11, 10, 0, 0)
    assert params[3] == datetime(2026, 11, 10, 2, 0)


def test_same_timestamp_twice_keeps_only_the_first_row(source, db):
    db.obs_rows = [
        (datetime(2026, 11, 10, 0, 0), 5.0, 100.0, 0),  # 가장 늦게 적재된 행이 먼저 온다(SQL 정렬)
        (datetime(2026, 11, 10, 0, 0), 9.0, 100.0, 0),
        (datetime(2026, 11, 10, 0, 30), 7.0, 100.0, 0),
    ]
    rows = source.observations(
        "100:1", "nox", datetime(2026, 11, 10, tzinfo=KST), datetime(2026, 11, 11, tzinfo=KST)
    )
    assert [r.value for r in rows] == [5.0, 7.0]


def test_two_name_history_keys_for_one_stack_are_queried_together(db, tick):
    db.stack_rows = [
        stack_row("경기도|옛이름|1", "100", "1", "㈜가나에너지"),
        stack_row("경기도|새이름|1", "100", "1", "㈜가나에너지"),
    ]
    source = RdsDataSource(db.connect, monotonic=tick)
    assert [s.stack_key for s in source.list_stacks()] == ["100:1"]
    source.observations(
        "100:1", "nox", datetime(2026, 11, 10, tzinfo=KST), datetime(2026, 11, 11, tzinfo=KST)
    )
    keys = db.calls[-1][1][0]
    assert sorted(keys) == ["경기도|새이름|1", "경기도|옛이름|1"]


def test_unknown_stack_returns_empty_without_querying_observations(source, db):
    rows = source.observations(
        "999:1", "nox", datetime(2026, 11, 10, tzinfo=KST), datetime(2026, 11, 11, tzinfo=KST)
    )
    assert rows == []
    assert db.count("obs.measurement_30m") == 0


def test_unknown_item_is_rejected(source):
    with pytest.raises(ValueError):
        source.observations(
            "100:1", "co", datetime(2026, 11, 10, tzinfo=KST), datetime(2026, 11, 11, tzinfo=KST)
        )


def test_as_of_is_cached_for_a_minute_and_empty_table_is_none(source, db, tick):
    db.max_at = datetime(2026, 11, 20, 9, 30)
    assert source.as_of() == datetime(2026, 11, 20, 9, 30, tzinfo=KST)
    db.max_at = datetime(2026, 11, 20, 10, 0)
    assert source.as_of() == datetime(2026, 11, 20, 9, 30, tzinfo=KST)  # 캐시
    tick.now += 61
    assert source.as_of() == datetime(2026, 11, 20, 10, 0, tzinfo=KST)
    empty = FakeDb()
    assert RdsDataSource(empty.connect, monotonic=tick).as_of() is None


def test_database_failure_becomes_data_source_unavailable_without_leaking_details(source, db):
    db.fail = True
    with pytest.raises(DataSourceUnavailable) as caught:
        source.list_stacks()
    assert "secret" not in str(caught.value)  # 문구에 접속 정보가 없다
    assert isinstance(caught.value.__cause__, ConnectionError)  # 원인은 체인에 남는다
    # 실패는 캐시하지 않는다: 복구되면 바로 읽힌다
    db.fail = False
    assert len(source.list_stacks()) == 4


def test_database_failure_during_a_chat_is_a_503_with_a_safe_message(
    source, db, monkeypatch, clock
):
    from fastapi.testclient import TestClient
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agent import api
    from app.agent.extractor import RuleExtractor
    from app.agent.graph import sites_from
    from app.agent.names import SiteResolver
    from app.agent.service import AgentService
    from app.main import app

    resolver = SiteResolver(sites_from(source))  # 목록은 읽힌다
    api.set_service(
        AgentService(RuleExtractor(resolver), source, InMemorySaver(), clock, "rule-dev")
    )
    monkeypatch.setenv("AUTH_DISABLED", "1")
    try:
        db.fail = True  # 이후 관측 조회가 실패한다
        response = TestClient(app).post(
            "/agent/chat", json={"message": "가나에너지 굴뚝 1 어제 NOx 평균 알려줘"}
        )
    finally:
        api.set_service(None)
    assert response.status_code == 503
    assert "secret" not in response.text  # 접속 정보가 응답에 없다
    assert "다시 시도" in response.json()["detail"]


def test_database_down_while_assembling_the_service_is_also_a_503(monkeypatch):
    from fastapi.testclient import TestClient

    from app.agent import api
    from app.main import app

    def broken():
        raise DataSourceUnavailable("RDS에서 읽지 못했다")

    monkeypatch.setattr(api, "_default_service", broken)
    monkeypatch.setenv("AUTH_DISABLED", "1")
    api.set_service(None)
    response = TestClient(app).post("/agent/chat", json={"message": "가나에너지 굴뚝 1"})
    assert response.status_code == 503
    assert "다시 시도" in response.json()["detail"]


def test_data_source_is_chosen_by_environment(monkeypatch):
    from app.agent import api, rds_connect
    from app.agent.data import InMemoryDataSource
    from app.agent.rds_data import RdsDataSource

    monkeypatch.delenv("AGENT_DATA_SOURCE", raising=False)
    monkeypatch.delenv("AGENT_LOCAL_DAY_DIR", raising=False)
    assert isinstance(api._data_source(), InMemoryDataSource)  # 설정이 없으면 지금과 같다

    class FakePool:
        def connection(self):
            return FakeDb()

    made = []
    monkeypatch.setattr(rds_connect, "make_pool", lambda: made.append(1) or FakePool())
    monkeypatch.setenv("AGENT_DATA_SOURCE", "rds")
    api._rds_pool.cache_clear()
    try:
        assert isinstance(api._data_source(), RdsDataSource)
        assert isinstance(api._data_source(), RdsDataSource)
        assert len(made) == 1  # 몇 번을 불러도 풀은 하나만 만든다
    finally:
        api._rds_pool.cache_clear()


def test_failure_in_observations_and_as_of_is_also_wrapped(source, db):
    source.list_stacks()
    db.fail = True
    with pytest.raises(DataSourceUnavailable):
        source.observations(
            "100:1", "nox", datetime(2026, 11, 10, tzinfo=KST), datetime(2026, 11, 11, tzinfo=KST)
        )
    with pytest.raises(DataSourceUnavailable):
        source.as_of()
