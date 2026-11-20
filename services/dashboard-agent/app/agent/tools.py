"""데이터 에이전트의 도구. 읽기 전용이고, 모델은 SQL을 쓰지 않는다.

평균·최댓값 같은 집계는 `status_code == 0`(정상 숫자)인 관측만으로 계산한다.
상태 행(미수신·보수 중 등)의 value는 0으로 저장될 수 있어 섞이면 가짜 0이 되기 때문이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.agent.slots import Period

OK = 0
NOT_MONITORED = 8
STATUS_LABEL = {
    1: "가동 중지(측정자료 확인 중)",
    2: "측정자료 확인 중",
    3: "미수신",
    4: "보수 중",
    5: "기기 점검",
    8: "측정하지 않는 물질",
    9: "같은 조합 충돌",
    99: "확인할 수 없는 상태",
}
# 원문 상태 문자열 → 상태 코드 (docs/D_SERVICE_TABLES_PROPOSAL_20261118_KO.md 3.3)
RAW_STATUS = {
    "측정자료확인중(가동중지)": 1,
    "측정자료확인중": 2,
    "미수신": 3,
    "보수중": 4,
    "기기점검": 5,
}


@dataclass(frozen=True)
class StackInfo:
    stack_key: str  # site_id:stack_code
    site_id: str
    business: str
    code: str
    region: str = ""
    sigungu: str = ""


@dataclass(frozen=True)
class Observation:
    measured_at: datetime
    value: float | None
    limit: float | None
    status_code: int


class DataSource(Protocol):
    def find_stacks(self, business: str, code: str | None) -> list[StackInfo]: ...

    def get_stack(self, stack_key: str) -> StackInfo | None: ...

    def list_stacks(self) -> list[StackInfo]: ...

    def observations(
        self, stack_key: str, item: str, start: datetime, end: datetime
    ) -> list[Observation]: ...

    def as_of(self) -> datetime | None: ...


@dataclass(frozen=True)
class AggregateResult:
    value: float | None
    n_used: int
    n_excluded: int  # 정상 숫자가 아닌 상태 행
    n_missing: int  # 행 자체가 없는 구간
    n_no_limit: int  # 값은 있으나 기준값이 없어 비율을 못 구한 행
    status_counts: dict[int, int] = field(default_factory=dict)
    unit: str = "ppm"


def aggregate_values(
    data: DataSource,
    stack_key: str,
    item: str,
    operation: str,
    metric: str,
    period: Period,
) -> AggregateResult:
    slots = period.slots()
    by_time = {
        o.measured_at: o for o in data.observations(stack_key, item, period.start, period.end)
    }
    used: list[float] = []
    status_counts: dict[int, int] = {}
    n_missing = n_no_limit = 0
    for slot in slots:
        row = by_time.get(slot)
        if row is None:
            n_missing += 1
            continue
        if row.status_code != OK or row.value is None:
            status_counts[row.status_code] = status_counts.get(row.status_code, 0) + 1
            continue
        if metric == "ratio":
            if row.limit is None or row.limit <= 0:
                n_no_limit += 1
                continue
            used.append(row.value / row.limit * 100)
        else:
            used.append(row.value)
    n_excluded = sum(status_counts.values())
    return AggregateResult(
        value=_reduce(used, operation),
        n_used=len(used),
        n_excluded=n_excluded,
        n_missing=n_missing,
        n_no_limit=n_no_limit,
        status_counts=status_counts,
        unit="%" if metric == "ratio" else "ppm",
    )


def _reduce(values: list[float], operation: str) -> float | None:
    if not values:
        return None
    if operation == "mean":
        return sum(values) / len(values)
    if operation == "max":
        return max(values)
    if operation == "min":
        return min(values)
    if operation == "sum":
        return sum(values)
    raise ValueError(f"지원하지 않는 집계: {operation}")


# ── 순위 ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RankRow:
    stack: StackInfo
    value: float
    n_used: int
    n_excluded: int
    n_missing: int


def rank_stacks(
    data: DataSource,
    item: str,
    operation: str,
    metric: str,
    period: Period,
    top_n: int,
    site_ids: set[str] | None = None,
    order: str | None = None,
) -> list[RankRow]:
    """전국 굴뚝을 기간 집계값으로 줄 세운다. 정상 숫자가 없는 굴뚝은 순위에서 뺀다.

    방향은 `order`(asc=낮은 순, desc=높은 순)로 정한다. 없으면 '최솟값'일 때만 낮은 순이고
    그 밖에는 높은 순이다. 같은 값이면 굴뚝 키 순서로 고정한다.
    운영(RDS)에서는 일일 요약 표를 읽는 구현으로 바꿀 자리다.
    """
    rows: list[RankRow] = []
    for stack in data.list_stacks():
        if site_ids is not None and stack.site_id not in site_ids:
            continue
        result = aggregate_values(data, stack.stack_key, item, operation, metric, period)
        if result.value is None:
            continue
        rows.append(
            RankRow(stack, result.value, result.n_used, result.n_excluded, result.n_missing)
        )
    ascending = order == "asc" if order else operation == "min"
    rows.sort(key=lambda r: (r.value if ascending else -r.value, r.stack.stack_key))
    return rows[:top_n]


# ── 결측 이유 ─────────────────────────────────────────────────────────
MISSING_ROW = -1  # 행 자체가 없는 구간
STATUS_LABEL[MISSING_ROW] = "수신 기록 없음"


@dataclass(frozen=True)
class GapRun:
    start: datetime
    end: datetime
    cause: int  # 상태 코드 또는 MISSING_ROW
    slots: int


@dataclass(frozen=True)
class GapReport:
    expected: int
    n_ok: int
    status_counts: dict[int, int]
    runs: list[GapRun]  # 긴 순서 상위 3개
    not_monitored: bool


def gap_report(data: DataSource, stack_key: str, item: str, period: Period) -> GapReport:
    slots = period.slots()
    by_time = {
        o.measured_at: o for o in data.observations(stack_key, item, period.start, period.end)
    }
    counts: dict[int, int] = {}
    runs: list[GapRun] = []
    current: GapRun | None = None
    n_ok = 0
    for slot in slots:
        row = by_time.get(slot)
        cause = MISSING_ROW if row is None else row.status_code
        if cause == OK:
            n_ok += 1
            if current:
                runs.append(current)
                current = None
            continue
        counts[cause] = counts.get(cause, 0) + 1
        if current and current.cause == cause:
            current = GapRun(current.start, slot, cause, current.slots + 1)
        else:
            if current:
                runs.append(current)
            current = GapRun(slot, slot, cause, 1)
    if current:
        runs.append(current)
    runs.sort(key=lambda r: (-r.slots, r.start))
    return GapReport(
        expected=len(slots),
        n_ok=n_ok,
        status_counts=counts,
        runs=runs[:3],
        not_monitored=counts.get(NOT_MONITORED, 0) == len(slots) and len(slots) > 0,
    )


# ── 지역 프로파일 (지역 평균이 왜 의미가 흐린지 근거를 만든다) ───────────────────
@dataclass(frozen=True)
class RegionProfile:
    n_sites: int
    n_stacks: int
    n_with_value: int  # 기간 안에 정상 숫자 관측이 하나라도 있는 굴뚝
    slots_total: int  # 굴뚝 수 x 기간 슬롯 수
    n_used: int  # 정상 수신 슬롯
    n_excluded: int  # 상태 행(미수신·보수 중 등)
    n_missing: int  # 행 자체가 없는 슬롯
    median: float | None  # 굴뚝별 평균값의 중앙값
    maximum: float | None  # 굴뚝별 평균값의 최대
    limit_min: float | None
    limit_max: float | None
    limit_kinds: int  # 서로 다른 허용기준 종류 수


def region_profile(
    data: DataSource, site_ids: set[str], item: str, period: Period
) -> RegionProfile:
    stacks = [s for s in data.list_stacks() if s.site_id in site_ids]
    values: list[float] = []
    limits: list[float] = []
    used = excluded = missing = 0
    for stack in stacks:
        result = aggregate_values(data, stack.stack_key, item, "mean", "value", period)
        used += result.n_used
        excluded += result.n_excluded
        missing += result.n_missing
        if result.value is None:
            continue
        values.append(result.value)
        for row in data.observations(stack.stack_key, item, period.start, period.end):
            if row.status_code == OK and row.limit:
                limits.append(row.limit)
                break
    ordered = sorted(values)
    median = ordered[len(ordered) // 2] if ordered else None
    return RegionProfile(
        n_sites=len(site_ids),
        n_stacks=len(stacks),
        n_with_value=len(values),
        slots_total=len(stacks) * len(period.slots()),
        n_used=used,
        n_excluded=excluded,
        n_missing=missing,
        median=median,
        maximum=max(values) if values else None,
        limit_min=min(limits) if limits else None,
        limit_max=max(limits) if limits else None,
        limit_kinds=len(set(limits)),
    )


# ── 파생 계산: 허용기준 초과, 극값 시각 ─────────────────────────────────────
@dataclass(frozen=True)
class ExceedResult:
    n_used: int  # 정상 숫자 관측 중 기준이 있는 것
    n_over: int  # 값 > 허용기준
    n_no_limit: int  # 기준 값이 없어 비교하지 못한 관측
    max_value: float | None
    limit_min: float | None
    limit_max: float | None
    longest_run: int  # 가장 길게 이어진 연속 초과 횟수
    run_start: datetime | None
    run_end: datetime | None


def _ordered(data: DataSource, stack_key: str, item: str, period: Period) -> list[Observation]:
    rows = data.observations(stack_key, item, period.start, period.end)
    return sorted(rows, key=lambda o: o.measured_at)


def exceedance(data: DataSource, stack_key: str, item: str, period: Period) -> ExceedResult:
    used = over = no_limit = 0
    limits: list[float] = []
    max_value: float | None = None
    run = best = 0
    run_start: datetime | None = None
    best_start: datetime | None = None
    best_end: datetime | None = None
    for row in _ordered(data, stack_key, item, period):
        if row.status_code != OK or row.value is None:
            run = 0
            continue
        if not row.limit or row.limit <= 0:
            no_limit += 1
            run = 0
            continue
        used += 1
        limits.append(row.limit)
        max_value = row.value if max_value is None else max(max_value, row.value)
        if row.value > row.limit:
            over += 1
            run += 1
            run_start = row.measured_at if run == 1 else run_start
            if run > best:
                best, best_start, best_end = run, run_start, row.measured_at
        else:
            run = 0
    return ExceedResult(
        used,
        over,
        no_limit,
        max_value,
        min(limits, default=None),
        max(limits, default=None),
        best,
        best_start,
        best_end,
    )


def extreme_time(
    data: DataSource, stack_key: str, item: str, operation: str, period: Period
) -> tuple[float, datetime] | None:
    """정상 숫자 관측 중 최댓값(또는 최솟값)과 그 시각. 같으면 먼저 나온 시각."""
    best: tuple[float, datetime] | None = None
    for row in _ordered(data, stack_key, item, period):
        if row.status_code != OK or row.value is None:
            continue
        if best is None:
            better = True
        elif operation == "min":
            better = row.value < best[0]
        else:
            better = row.value > best[0]
        if better:
            best = (row.value, row.measured_at)
    return best
