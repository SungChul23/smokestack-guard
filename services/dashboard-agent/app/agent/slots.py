"""조회 조건(칸)과 시간 해석. 모델은 칸 값만 제안하고, 빠진 칸·기간은 코드가 계산한다.

칸: stack(굴뚝), pollutants(물질), time(기간), operation(집계), metric(값/기준대비율).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, TypedDict

KST = timezone(timedelta(hours=9))
STEP = timedelta(minutes=30)
POLLUTANTS = ("nox", "sox")
POLLUTANT_LABEL = {"nox": "NOx", "sox": "SOx"}
OPERATIONS = ("mean", "max", "min", "sum")
OPERATION_LABEL = {"mean": "평균", "max": "최댓값", "min": "최솟값", "sum": "합계"}
SLOT_NAMES = ("stack", "pollutants", "time", "operation", "metric")
INTENTS = ("aggregate", "rank", "freshness", "gap")
# 유형별로 질문에 꼭 있어야 하는 칸(빠지면 되묻는다).
# 순위의 집계 방식은 기본 최댓값이라 묻지 않는다.
REQUIRED = {
    "aggregate": ("stack", "pollutants", "time", "operation"),
    "rank": ("pollutants", "time"),
    "freshness": (),
    "gap": ("stack", "pollutants", "time"),
}
DEFAULT_TOP_N = 5
MAX_TOP_N = 10

_CORPORATE = re.compile(r"주식회사|\(주\)|\(유\)|\(사\)|\(재\)|\(합\)")


class StackSlot(TypedDict, total=False):
    business: str | None
    code: str | None
    site_id: str | None
    stack_key: str | None


class TimeSlot(TypedDict, total=False):
    kind: Literal["yesterday", "today", "now", "date", "hours", "other"]
    value: str | int | None


class Command(TypedDict, total=False):
    """확정되었거나 확정 중인 조회 조건."""

    stack: StackSlot | None
    pollutants: list[str]
    time: TimeSlot | None
    operation: str | None
    metric: str
    intent: str
    top_n: int
    order: str  # 순위를 줄 세우는 방향: asc(낮은 순) | desc(높은 순). 없으면 집계가 min이면 asc
    site_ids: list[str]  # 순위를 볼 사업장 범위(지역 안 순위)
    scope_label: str  # 그 범위의 이름(답변 머리말)


# 순위의 방향은 집계 방식("평균", "최솟값")과 따로 말한다: "평균이 가장 낮은", "최솟값이 가장 높은".
_ORDER_LOW = re.compile(
    r"(?:가장|제일|젤)\s*(?:낮|적|작)|(?:낮은|적은|작은)\s*(?:순|쪽|굴뚝|곳|사업장|값)|하위|꼴찌|바닥"
)
_ORDER_HIGH = re.compile(
    r"(?:가장|제일|젤)\s*(?:높|많|크|큰)|(?:높은|많은|큰)\s*(?:순|쪽|굴뚝|곳|사업장|값)|상위"
)


def rank_order(text: str) -> str | None:
    """순위 질문의 방향. 낮은 쪽만 말했으면 asc, 높은 쪽만 말했으면 desc, 말이 없거나 섞이면 None.

    None이면 집계가 min일 때만 낮은 순이고 그 밖에는 높은 순이다(예전 동작)."""
    low = _ORDER_LOW.search(text) is not None
    high = _ORDER_HIGH.search(text) is not None
    if low and not high:
        return "asc"
    if high and not low:
        return "desc"
    return None


def norm_name(text: str | None) -> str:
    """사업장 이름 비교용 정규화: NFKC(㈜ → (주)), 법인 표기·공백·기호 제거, 소문자."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text)
    folded = _CORPORATE.sub("", folded)
    return re.sub(r"[\s()\-·.,]", "", folded).lower()


@dataclass(frozen=True)
class Period:
    start: datetime  # 포함
    end: datetime  # 미포함
    label: str

    def slots(self) -> list[datetime]:
        out, t = [], self.start
        while t < self.end:
            out.append(t)
            t += STEP
        return out


class UnsupportedPeriod(ValueError):
    pass


def floor_step(t: datetime) -> datetime:
    return t.replace(minute=0 if t.minute < 30 else 30, second=0, microsecond=0)


def resolve_period(spec: TimeSlot | None, now: datetime) -> Period:
    """기간 칸을 시작·끝 시각으로 바꾼다. 지원하지 않는 표현은 UnsupportedPeriod."""
    if not spec or not spec.get("kind"):
        raise UnsupportedPeriod("기간이 없다")
    kind, value = spec["kind"], spec.get("value")
    now = now.astimezone(KST)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "yesterday":
        start = midnight - timedelta(days=1)
        return Period(start, midnight, f"{start:%Y-%m-%d} 하루")
    if kind == "today":
        return Period(midnight, floor_step(now) + STEP, f"{midnight:%Y-%m-%d} 현재까지")
    if kind == "date":
        try:
            start = datetime.strptime(str(value), "%Y-%m-%d").replace(tzinfo=KST)
        except ValueError as error:
            raise UnsupportedPeriod("날짜 형식이 맞지 않는다") from error
        return Period(start, start + timedelta(days=1), f"{start:%Y-%m-%d} 하루")
    if kind == "hours":
        try:
            hours = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as error:
            raise UnsupportedPeriod("시간 수가 맞지 않는다") from error
        if not 1 <= hours <= 72:
            raise UnsupportedPeriod("지난 1~72시간만 지원한다")
        end = floor_step(now) + STEP
        return Period(end - timedelta(hours=hours), end, f"지난 {hours}시간")
    raise UnsupportedPeriod(f"지원하지 않는 기간 표현: {kind}")


def missing_slots(command: Command) -> list[str]:
    """되물어야 하는 칸. 순서는 되묻는 순서다(굴뚝 → 물질 → 기간 → 집계)."""
    missing: list[str] = []
    stack = command.get("stack") or {}
    for name in REQUIRED.get(command.get("intent") or "aggregate", REQUIRED["aggregate"]):
        if name == "stack" and not (stack.get("stack_key") or stack.get("business")):
            missing.append(name)
        elif name in ("pollutants", "time", "operation") and not command.get(name):
            missing.append(name)
    return missing


def merge_command(base: Command | None, extracted: dict, patch: list[str] | None) -> Command:
    """직전 조건(base)에 이번 질문에서 뽑은 칸을 합친다.

    patch가 있으면(후속 질문) 질문이 바꾸는 칸만 덮어쓰고 나머지는 이어받는다.
    patch가 없으면 질문에 실제로 적힌 칸만 새 조건으로 쓴다.
    """
    result: Command = {"metric": "value"}
    if patch is not None and base:
        result = {**base}
        names = [name for name in patch if name in SLOT_NAMES]
    else:
        names = list(SLOT_NAMES)
    for name in names:
        value = extracted.get(name)
        if value in (None, [], {}):
            continue
        result[name] = value  # type: ignore[literal-required]
    result.setdefault("metric", "value")
    return result
