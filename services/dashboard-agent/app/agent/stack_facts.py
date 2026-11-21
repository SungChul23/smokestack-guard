"""굴뚝의 지정 기준(ppm)과 최근 측정값을 도구로 읽어 문장으로 만든다.

법령 요약 답변에 "이 굴뚝의 기준은 ○ppm, 최근 24시간 최댓값은 ○ppm"을 붙이는 데 쓴다.
숫자는 코드가 읽어 쓴다. 요약 모델은 이 숫자를 만들지 않는다(모델은 맥락으로만 받는다).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.agent.slots import Period
from app.agent.tools import OK, DataSource

ITEMS = (("nox", "NOx"), ("sox", "SOx"))
RECENT_HOURS = 24


@dataclass(frozen=True)
class ItemFacts:
    pollutant: str
    limit: float | None  # 자료에 있는 지정 기준(ppm). 없으면 None
    n_used: int  # 정상 숫자 관측 수
    latest_value: float | None
    latest_at: datetime | None
    max_value: float | None
    n_over: int  # 값 > 기준인 관측 수(기준이 있을 때)


@dataclass(frozen=True)
class StackFacts:
    stack_key: str
    label: str  # "사업장 굴뚝 N"
    period_label: str
    items: tuple[ItemFacts, ...] = field(default_factory=tuple)


def _num(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def collect_stack_facts(
    data: DataSource, stack_key: str, now: datetime, hours: int = RECENT_HOURS
) -> StackFacts | None:
    """굴뚝의 최근 `hours`시간(자료의 마지막 시각 기준) 사실. 굴뚝을 모르면 None."""
    info = data.get_stack(stack_key)
    if info is None:
        return None
    end = data.as_of() or now
    period = Period(end - timedelta(hours=hours), end + timedelta(minutes=30), f"최근 {hours}시간")
    items: list[ItemFacts] = []
    for item, label in ITEMS:
        rows = sorted(
            data.observations(stack_key, item, period.start, period.end),
            key=lambda o: o.measured_at,
        )
        good = [r for r in rows if r.status_code == OK and r.value is not None]
        limits = [r.limit for r in rows if r.limit and r.limit > 0]
        if not rows or (not good and not limits):
            continue  # 측정하지 않는 물질이거나 자료가 없다
        limit = limits[-1] if limits else None
        latest = good[-1] if good else None
        over = sum(1 for r in good if limit and r.value > limit)  # type: ignore[operator]
        items.append(
            ItemFacts(
                pollutant=label,
                limit=limit,
                n_used=len(good),
                latest_value=latest.value if latest else None,
                latest_at=latest.measured_at if latest else None,
                max_value=max((r.value for r in good), default=None),  # type: ignore[type-var]
                n_over=over,
            )
        )
    return StackFacts(stack_key, f"{info.business} 굴뚝 {info.code}", period.label, tuple(items))


def facts_text(facts: StackFacts) -> str:
    """응답에 붙일 문장. 모든 숫자는 자료에서 읽은 값이다."""
    if not facts.items:
        return (
            f"{facts.label}: {facts.period_label} 측정 자료가 없어 "
            "기준·측정값을 보여 드릴 수 없습니다."
        )
    lines = [f"[{facts.label}의 지정 기준과 {facts.period_label} 측정값]"]
    for it in facts.items:
        limit = f"지정 기준 {_num(it.limit)} ppm" if it.limit else "지정 기준값은 자료에 없음"
        if it.max_value is None:
            lines.append(f"- {it.pollutant}: {limit}, 정상 측정값 없음")
            continue
        text = f"- {it.pollutant}: {limit}, 최댓값 {_num(it.max_value)} ppm"
        if it.latest_value is not None and it.latest_at is not None:
            text += f", 최근값 {_num(it.latest_value)} ppm({it.latest_at:%m-%d %H:%M})"
        if it.limit:
            text += f", 기준 초과 관측 {it.n_over}건 (정상 관측 {it.n_used}건 중)"
        lines.append(text)
    lines.append("이 수치는 측정 자료이며 위반·처분 여부를 판단하지 않습니다.")
    return "\n".join(lines)
