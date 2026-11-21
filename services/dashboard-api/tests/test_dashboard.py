"""화면용 읽기 라우트·즐겨찾기 (spec 318). DB는 가짜 연결로 대신한다."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import dashboard
from app.db import DbUnavailable, get_conn
from app.main import app
from tests.test_auth import cognito as _cognito  # noqa: F401  (autouse 픽스처)
from tests.test_auth import token

LATEST = datetime(2026, 11, 10, 23, 30)
client = TestClient(app)


def member(**over):
    return {"Authorization": f"Bearer {token(**{'cognito:groups': ['members']} | over)}"}


# ── 순수 함수 ────────────────────────────────────────────────────

STACKS = [("a|S1|1", "100", "1"), ("a|S1|1b", "100", "1"), ("b|S2|2", "200", "2")]


def test_stack_keys_make_unique_screen_keys():
    keys = dashboard.stack_keys(STACKS)
    assert keys["a|S1|1"][0] == "100:1"
    assert keys["a|S1|1b"][0] == "100:1-2"  # 같은 사업장·번호가 겹치면 -2
    assert keys["b|S2|2"] == ("200:2", "2")


def test_build_sites_shortens_sido_and_skips_without_coordinates():
    keys = dashboard.stack_keys(STACKS)
    rows = [
        ("100", "가공장", "서울특별시", None, "서울특별시 중구 세종대로 1", 37.5, 127.0, "a|S1|1"),
        ("100", "가공장", "서울특별시", None, "서울특별시 중구 세종대로 1", 37.5, 127.0, "a|S1|1b"),
        ("200", "나공장", "경기도", "수원시", "", None, None, "b|S2|2"),  # 좌표 없음
    ]
    sites = dashboard.build_sites(rows, keys)
    assert len(sites) == 1
    assert sites[0] | {"stacks": None} == {
        "id": "100",
        "name": "가공장",
        "sido": "서울",
        "sigungu": "중구",
        "address": "서울특별시 중구 세종대로 1",
        "lon": 127.0,
        "lat": 37.5,
        "stacks": None,
    }
    assert [s["key"] for s in sites[0]["stacks"]] == ["100:1", "100:1-2"]


def test_build_day_48_slots_raw_text_and_latest_limit():
    keys = dashboard.stack_keys(STACKS)
    t = lambda n: LATEST - timedelta(minutes=30 * n)  # noqa: E731
    rows = [
        ("a|S1|1", "nox", t(0), 45.2, 100.0, None, "값", 0),
        (
            "a|S1|1",
            "nox",
            t(1),
            None,
            None,
            "미수신",
            "미수신",
            3,
        ),  # 상태 칸: 값은 null, 문구를 준다
        ("a|S1|1", "nox", t(2), 40.0, 90.0, None, "값", 0),  # 정수 값은 .0 없이
        ("a|S1|1", "sox", t(0), 10.0, 50.0, None, "값", 0),
        ("a|S1|1", "nox", t(60), 1.0, 1.0, None, "값", 0),  # 창 밖은 버린다
        ("zz|X|9", "nox", t(0), 1.0, 1.0, None, "값", 0),  # 사업장 연결 없는 굴뚝
    ]
    day = dashboard.build_day(LATEST, rows, keys)
    assert len(day["times"]) == 48
    assert day["times"][-1] - day["times"][-2] == 30 * 60 * 1000
    assert day["times"][-1] == dashboard.epoch_ms(LATEST)
    s = day["stacks"]["100:1"]
    assert s["nox"][47] == "45.2" and s["nox"][46] == "미수신" and s["nox"][45] == "40"
    assert s["noxLimit"] == "100" and s["soxLimit"] == "50"  # 가장 최근 기준값
    assert s["nox"][0] is None
    assert list(day["stacks"]) == ["100:1"]
    assert "noxLimitAt" not in s


def test_epoch_is_kst():
    assert dashboard.epoch_ms(datetime(1970, 1, 1, 9, 0)) == 0  # 한국 09:00 = UTC 00:00


# ── 라우트 ───────────────────────────────────────────────────────


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    def __init__(self, tables=None):
        self.tables = tables or {}
        self.sql: list[tuple] = []
        self.favs: set[tuple] = set()
        self.commits = 0

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        s = " ".join(sql.split())
        if s.startswith("SELECT target FROM app.user_favorite"):
            return FakeResult([(t,) for (u, t) in sorted(self.favs) if u == params[0]])
        if s.startswith("INSERT INTO app.user_favorite"):
            self.favs.add(tuple(params))
        elif s.startswith("DELETE FROM app.user_favorite"):
            self.favs.discard(tuple(params))
        elif s.startswith("SELECT max(measured_at)"):
            return FakeResult([(self.tables.get("latest"),)])
        elif "FROM ref.v_stack WHERE" in s:
            return FakeResult(STACKS)
        elif "FROM ref.site si" in s:
            return FakeResult(self.tables.get("sites", []))
        elif "FROM obs.measurement_30m m" in s:
            return FakeResult(self.tables.get("rows", []))
        return FakeResult([])

    def commit(self):
        self.commits += 1


@pytest.fixture
def conn():
    dashboard._cache.clear()
    c = FakeConn(
        {
            "latest": LATEST,
            "sites": [("100", "가공장", "서울특별시", "중구", "", 37.5, 127.0, "a|S1|1")],
            "rows": [("a|S1|1", "nox", LATEST, 45.2, 100.0, None, "값", 0)],
        }
    )
    app.dependency_overrides[get_conn] = lambda: c
    yield c
    app.dependency_overrides.clear()


def test_routes_need_login_and_membership(conn):
    assert client.get("/api/sites").status_code == 401
    r = client.get(
        "/api/sites", headers={"Authorization": f"Bearer {token()}"}
    )  # 로그인은 했지만 회원이 아님
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_member"


def test_sites_and_day(conn):
    r = client.get("/api/sites", headers=member())
    assert r.status_code == 200 and r.json()[0]["stacks"] == [{"key": "100:1", "code": "1"}]
    d = client.get("/api/day", headers=member()).json()
    assert len(d["times"]) == 48 and d["stacks"]["100:1"]["nox"][47] == "45.2"


def test_day_is_cached_while_latest_slot_is_the_same(conn):
    client.get("/api/day", headers=member())
    n = sum("FROM obs.measurement_30m m" in " ".join(q[0].split()) for q in conn.sql)
    client.get("/api/day", headers=member())
    client.get("/api/day", headers=member())
    assert sum("FROM obs.measurement_30m m" in " ".join(q[0].split()) for q in conn.sql) == n == 1
    conn.tables["latest"] = LATEST + timedelta(minutes=30)  # 새 시각이 적재되면 다시 만든다
    client.get("/api/day", headers=member())
    assert sum("FROM obs.measurement_30m m" in " ".join(q[0].split()) for q in conn.sql) == 2


def test_day_without_observations_is_404(conn):
    conn.tables["latest"] = None
    r = client.get("/api/day", headers=member())
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_data"


def test_db_off_is_503(conn):
    def boom():
        raise DbUnavailable("DB가 꺼져 있다 (DB_HOST 없음)")
        yield  # pragma: no cover

    app.dependency_overrides[get_conn] = boom
    r = client.get("/api/sites", headers=member())
    assert r.status_code == 503


def test_favorites_are_per_user_sub(conn):
    h1, h2 = member(sub="u1"), member(sub="u2")
    assert client.get("/api/favorites", headers=h1).json() == {"targets": []}
    assert client.put("/api/favorites/100", headers=h1).json() == {"targets": ["100"]}
    client.put("/api/favorites/100", headers=h1)  # 두 번 눌러도 그대로
    client.put("/api/favorites/200", headers=h2)
    assert client.get("/api/favorites", headers=h1).json() == {"targets": ["100"]}
    assert client.get("/api/favorites", headers=h2).json() == {"targets": ["200"]}
    assert client.delete("/api/favorites/100", headers=h1).json() == {"targets": []}
    assert conn.commits >= 3


def test_favorite_target_is_validated(conn):
    assert client.put("/api/favorites/" + "x" * 300, headers=member()).status_code == 400
