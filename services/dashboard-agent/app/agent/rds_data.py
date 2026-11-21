"""RDS 데이터 소스: `DataSource`(tools.py)를 RDS(`ref`·`obs`)에서 읽어 구현한다 (spec 316).

- 읽기 전용이다. 이 모듈은 SELECT만 보낸다(접속 계정도 읽기 전용 `tms_app`, rds_connect.py).
- 굴뚝 목록은 시작할 때 한 번 읽고 `stack_ttl`초마다 새로 읽는다.
  관측은 질문마다 기본키 구간으로 조회한다.
- 에이전트의 굴뚝 키는 `"{site_id}:{굴뚝번호}"`이고 RDS의 키는 `"지역|사업장|굴뚝번호"`다.
  사업장 코드가 없는 굴뚝(`ref.v_stack.site_id`가 null)은 목록에서 빠진다.
- 상태 코드는 RDS `ref.status_code`와 에이전트 `tools.py`가 같은 체계라 바꾸지 않는다.
  상태 행의 `value`는 RDS에서 null이고, 계산 도구는 `status_code != OK or value is None`
  행을 거른다.
- 시각은 RDS에서 KST 벽시계(시간대 없음)다. 에이전트 쪽에서는 `tzinfo=KST`를 붙여 돌려준다.
- 연결 방식은 주입받는다(`connect`). 시험에서는 가짜 연결을,
  운영에서는 rds_connect.make_pool().connection을 쓴다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol

from app.agent.slots import KST, norm_name
from app.agent.tools import Observation, StackInfo

ITEMS = ("nox", "sox")

STACKS_SQL = """
SELECT v.stack_key, v.site_id, v.stack_code, s.display_name, s.region_sido, s.region_sigungu
FROM ref.v_stack v
JOIN ref.site s ON s.site_id = v.site_id
"""

OBSERVATIONS_SQL = """
SELECT measured_at, value, limit_value, status_code
FROM obs.measurement_30m
WHERE stack_key = ANY(%s) AND item = %s AND measured_at >= %s AND measured_at < %s
ORDER BY measured_at, loaded_at DESC
"""

AS_OF_SQL = "SELECT max(measured_at) FROM obs.measurement_30m"


class DataSourceUnavailable(RuntimeError):
    """데이터를 읽지 못했다(DB 연결·조회 실패). 원인은 `__cause__`에 있다."""


class _Connection(Protocol):
    def execute(self, query: str, params: Any = None) -> Any: ...


Connect = Callable[[], AbstractContextManager[_Connection]]


def _naive_kst(moment: datetime) -> datetime:
    """RDS 비교용: 시간대가 있으면 KST로 바꾼 뒤 벽시계로, 없으면 KST 벽시계로 본다."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(KST).replace(tzinfo=None)


def _stack_order(stack: StackInfo) -> tuple[str, int, str]:
    number = int(stack.code) if stack.code.isdigit() else 10**9
    return (stack.site_id, number, stack.code)


class RdsDataSource:
    def __init__(
        self,
        connect: Connect,
        *,
        stack_ttl: float = 3600.0,
        as_of_ttl: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connect = connect
        self._stack_ttl = stack_ttl
        self._as_of_ttl = as_of_ttl
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._stacks: dict[str, StackInfo] = {}
        self._rds_keys: dict[str, list[str]] = {}
        self._stacks_at: float | None = None
        self._as_of: datetime | None = None
        self._as_of_at: float | None = None

    # ── DB 접근 (여기서만 입출력 오류를 한 가지로 묶는다) ───────────────────
    def _query(self, sql: str, params: tuple | None = None) -> list[tuple]:
        try:
            with self._connect() as conn:
                return list(conn.execute(sql, params).fetchall())
        except Exception as error:  # noqa: BLE001  접속·권한·시간 초과 모두 같은 처리
            raise DataSourceUnavailable("RDS에서 읽지 못했다") from error

    # ── 굴뚝 목록 ─────────────────────────────────────────────────────────
    def _fresh(self, loaded_at: float | None, ttl: float) -> bool:
        return loaded_at is not None and self._monotonic() - loaded_at < ttl

    def _ensure_stacks(self) -> None:
        if self._fresh(self._stacks_at, self._stack_ttl):
            return
        with self._lock:
            if self._fresh(self._stacks_at, self._stack_ttl):
                return
            rows = self._query(STACKS_SQL)
            stacks: dict[str, StackInfo] = {}
            rds_keys: dict[str, list[str]] = {}
            for rds_key, site_id, code, name, region, sigungu in rows:
                key = f"{site_id}:{code}"
                stacks.setdefault(
                    key, StackInfo(key, site_id, name, str(code), region or "", sigungu or "")
                )
                rds_keys.setdefault(key, []).append(rds_key)
            ordered = sorted(stacks.values(), key=_stack_order)
            self._stacks = {s.stack_key: s for s in ordered}
            self._rds_keys = rds_keys
            self._stacks_at = self._monotonic()

    def list_stacks(self) -> list[StackInfo]:
        self._ensure_stacks()
        return list(self._stacks.values())

    def get_stack(self, stack_key: str) -> StackInfo | None:
        self._ensure_stacks()
        return self._stacks.get(stack_key)

    def find_stacks(self, business: str, code: str | None) -> list[StackInfo]:
        self._ensure_stacks()
        key = norm_name(business)
        return [
            s
            for s in self._stacks.values()
            if norm_name(s.business) == key and (code is None or s.code == str(code))
        ]

    # ── 관측 ──────────────────────────────────────────────────────────────
    def observations(
        self, stack_key: str, item: str, start: datetime, end: datetime
    ) -> list[Observation]:
        if item not in ITEMS:
            raise ValueError(f"알 수 없는 물질: {item}")
        self._ensure_stacks()
        rds_keys = self._rds_keys.get(stack_key)
        if not rds_keys:
            return []
        rows = self._query(OBSERVATIONS_SQL, (rds_keys, item, _naive_kst(start), _naive_kst(end)))
        out: list[Observation] = []
        seen: set[datetime] = set()
        for measured_at, value, limit, status_code in rows:
            # 같은 굴뚝 키가 이름 이력으로 둘 이상 연결된 드문 경우:
            # 같은 시각은 가장 늦게 적재된 한 행만 쓴다.
            if measured_at in seen:
                continue
            seen.add(measured_at)
            out.append(
                Observation(
                    measured_at.replace(tzinfo=KST),
                    None if value is None else float(value),
                    None if limit is None else float(limit),
                    int(status_code),
                )
            )
        return out

    def as_of(self) -> datetime | None:
        if self._fresh(self._as_of_at, self._as_of_ttl):
            return self._as_of
        rows = self._query(AS_OF_SQL)
        latest = rows[0][0] if rows else None
        self._as_of = None if latest is None else latest.replace(tzinfo=KST)
        self._as_of_at = self._monotonic()
        return self._as_of
