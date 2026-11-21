"""대시보드 화면용 읽기 라우트 + 즐겨찾기 (D, spec 318).

화면이 기대하는 모양(services/dashboard-web/src/data/model.ts)을 RDS(ref·obs)에서 만든다.
- GET /api/sites            사업장 목록(굴뚝 포함). 자주 안 바뀌어 10분 캐시.
- GET /api/day              최신 시각 기준 30분 48칸(24시간)의 굴뚝별 NOx·SOx 원문.
                           적재가 30분마다라 최신 시각이 같으면 캐시를 쓴다.
- GET/PUT/DELETE /api/favorites[/{target}]  Cognito sub 기준 즐겨찾기(app.user_favorite).
측정값이 없는 칸은 0이 아니라 상태 문구(미수신 등)나 null로 준다(012 data-model).
모든 라우트는 로그인한 회원만(CurrentUser).
"""

import logging
import time
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import CurrentUser
from app.db import get_conn
from app.logging_mw import log_activity

log = logging.getLogger("tms.api.dashboard")
router = APIRouter(prefix="/api")

SLOTS = 48
STEP = timedelta(minutes=30)
KST = timezone(timedelta(hours=9))

# 화면 지역 이름(짧은 이름). 목록에 전체 이름이 오면 줄여 준다.
SHORT = {
    "서울특별시": "서울",
    "인천광역시": "인천",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "대전광역시": "대전",
    "세종특별자치시": "세종",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "광주광역시": "광주",
    "경상북도": "경북",
    "경상남도": "경남",
    "대구광역시": "대구",
    "부산광역시": "부산",
    "울산광역시": "울산",
    "제주특별자치도": "제주",
}

Conn = Annotated[object, Depends(get_conn)]


def _rows(conn, sql: str, params: Sequence = ()) -> list:
    return conn.execute(sql, params).fetchall()


# ── 순수 함수(시험하기 쉽게 DB와 분리) ───────────────────────────────


def sigungu_of(address: str | None, given: str | None) -> str:
    if given:
        return given
    tokens = (address or "").split()
    t = tokens[1] if len(tokens) > 1 else ""
    return t if t and t[-1] in "시군구" else "기타"


def stack_keys(stack_rows: Sequence[tuple]) -> dict[str, tuple[str, str]]:
    """(stack_key, site_id, stack_code) → {stack_key: (화면 키, 굴뚝번호)}.
    같은 사업장·번호가 겹치면 -2, -3…"""
    out: dict[str, tuple[str, str]] = {}
    used: set[str] = set()
    for stack_key, site_id, code in sorted(stack_rows, key=lambda r: (r[1], str(r[2]), r[0])):
        key = f"{site_id}:{code}"
        n = 2
        while key in used:
            key = f"{site_id}:{code}-{n}"
            n += 1
        used.add(key)
        out[stack_key] = (key, key.split(":", 1)[1])
    return out


def build_sites(site_rows: Sequence[tuple], keys: dict[str, tuple[str, str]]) -> list[dict]:
    """site_rows: (site_id, 이름, 시도, 시군구, 주소, lat, lon, stack_key)."""
    sites: dict[str, dict] = {}
    for site_id, name, sido, sigungu, address, lat, lon, stack_key in site_rows:
        if lat is None or lon is None or stack_key not in keys:
            continue
        s = sites.setdefault(
            site_id,
            {
                "id": site_id,
                "name": name,
                "sido": SHORT.get(sido or "", sido or "기타"),
                "sigungu": sigungu_of(address, sigungu),
                "address": address or "",
                "lon": lon,
                "lat": lat,
                "stacks": [],
            },
        )
        key, code = keys[stack_key]
        s["stacks"].append({"key": key, "code": code})
    return [s for s in sites.values() if s["stacks"]]


def _raw(value, source_text, display_ko, status_code) -> str | None:
    """화면이 받는 원문: 정상 칸은 숫자 문자열, 상태 칸은 상태 문구. 값이 없는 정상 칸은 null."""
    if status_code == 0:
        return None if value is None else repr(float(value)).removesuffix(".0")
    return source_text or display_ko


def epoch_ms(naive_kst: datetime) -> int:
    return int(naive_kst.replace(tzinfo=KST).timestamp() * 1000)


def build_day(latest: datetime, rows: Sequence[tuple], keys: dict[str, tuple[str, str]]) -> dict:
    """rows: (stack_key, item, 시각, 값, 기준값, 원문 상태, 표시 문구, 상태 번호)."""
    slots = [latest - STEP * (SLOTS - 1 - i) for i in range(SLOTS)]
    index = {t: i for i, t in enumerate(slots)}
    stacks: dict[str, dict] = {}
    for stack_key, item, at, value, limit, source_text, display_ko, status_code in rows:
        i, k = index.get(at), keys.get(stack_key)
        if i is None or k is None or item not in ("nox", "sox"):
            continue
        e = stacks.setdefault(
            k[0],
            {
                "nox": [None] * SLOTS,
                "sox": [None] * SLOTS,
                "noxLimit": None,
                "soxLimit": None,
            },
        )
        e[item][i] = _raw(value, source_text, display_ko, status_code)
        if limit is not None and e.get(f"{item}LimitAt", slots[0] - STEP) <= at:
            e[f"{item}Limit"] = repr(float(limit)).removesuffix(".0")
            e[f"{item}LimitAt"] = at  # 가장 최근 기준값을 쓴다
    for e in stacks.values():
        e.pop("noxLimitAt", None)
        e.pop("soxLimitAt", None)
    return {"times": [epoch_ms(t) for t in slots], "stacks": stacks}


# ── 캐시: 적재가 30분마다라 같은 시각의 응답은 모두에게 같다 ─────────────

_cache: dict[str, tuple] = {}


def _cached(name: str, token, ttl: float, make):
    hit = _cache.get(name)
    now = time.monotonic()
    if hit and hit[0] == token and now - hit[1] < ttl:
        return hit[2]
    value = make()
    _cache[name] = (token, now, value)
    return value


STACK_SQL = "SELECT stack_key, site_id, stack_code FROM ref.v_stack WHERE site_id IS NOT NULL"
SITE_SQL = """
SELECT si.site_id, si.display_name, si.region_sido, si.region_sigungu,
       si.address, si.lat, si.lon, st.stack_key
FROM ref.site si JOIN ref.v_stack st ON st.site_id = si.site_id
WHERE si.lat IS NOT NULL AND si.lon IS NOT NULL
"""
LATEST_SQL = "SELECT max(measured_at) FROM obs.measurement_30m"
DAY_SQL = """
SELECT m.stack_key, m.item, m.measured_at, m.value, m.limit_value,
       c.source_text, c.display_ko, m.status_code
FROM obs.measurement_30m m JOIN ref.status_code c ON c.code = m.status_code
WHERE m.measured_at > %s AND m.measured_at <= %s
"""


@router.get("/sites")
def sites(user: CurrentUser, conn: Conn) -> list[dict]:
    def make():
        keys = stack_keys(_rows(conn, STACK_SQL))
        return build_sites(_rows(conn, SITE_SQL), keys)

    return _cached("sites", None, 600, make)


@router.get("/day")
def day(user: CurrentUser, conn: Conn) -> dict:
    latest = conn.execute(LATEST_SQL).fetchone()[0]
    if latest is None:
        raise HTTPException(
            status_code=404, detail={"code": "no_data", "message": "관측이 아직 없다"}
        )

    def make():
        keys = stack_keys(_rows(conn, STACK_SQL))
        rows = _rows(conn, DAY_SQL, (latest - STEP * SLOTS, latest))
        return build_day(latest, rows, keys)

    return _cached("day", latest, 3600, make)


# ── 즐겨찾기 (app.user_favorite: user_sub, target) ──────────────────────

MAX_TARGET = 200


class Favorites(BaseModel):
    targets: list[str]


def _target(value: str) -> str:
    t = value.strip()
    if not t or len(t) > MAX_TARGET:
        raise HTTPException(
            status_code=400, detail={"code": "invalid_target", "message": "대상 이름이 맞지 않는다"}
        )
    return t


@router.get("/favorites")
def favorites(user: CurrentUser, conn: Conn) -> Favorites:
    rows = _rows(
        conn,
        "SELECT target FROM app.user_favorite WHERE user_sub = %s ORDER BY created_at, target",
        (user["sub"],),
    )
    return Favorites(targets=[r[0] for r in rows])


@router.put("/favorites/{target:path}")
def add_favorite(target: str, user: CurrentUser, conn: Conn) -> Favorites:
    conn.execute(
        "INSERT INTO app.user_favorite (user_sub, target) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user["sub"], _target(target)),
    )
    conn.commit()
    log_activity("favorite_add", user["sub"], target=_target(target))  # 사용 현황 (A, 014)
    return favorites(user, conn)


@router.delete("/favorites/{target:path}")
def remove_favorite(target: str, user: CurrentUser, conn: Conn) -> Favorites:
    conn.execute(
        "DELETE FROM app.user_favorite WHERE user_sub = %s AND target = %s",
        (user["sub"], _target(target)),
    )
    conn.commit()
    log_activity("favorite_remove", user["sub"], target=_target(target))  # 사용 현황 (A, 014)
    return favorites(user, conn)
