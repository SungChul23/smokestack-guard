"""일일 요약 리포트. 이미 있는 도구로 계산한 값만 조립한다. 모델이 문장을 쓰지 않는다."""

from __future__ import annotations

from datetime import datetime

from app.agent.contract import Number, Part
from app.agent.slots import POLLUTANT_LABEL, Period
from app.agent.tools import DataSource, aggregate_values, exceedance, rank_stacks
from app.agent.verify import format_value

TOP = 3


def run_report(data: DataSource, period: Period, as_of: datetime | None) -> Part:
    stacks = data.list_stacks()
    lines = [f"{period.label} 전국 요약 (총 굴뚝 {len(stacks)}개)"]
    numbers: list[Number] = []
    for item in ("nox", "sox"):
        label = POLLUTANT_LABEL[item]
        used = total = with_value = over_stacks = 0
        slots = len(period.slots())
        for stack in stacks:
            r = aggregate_values(data, stack.stack_key, item, "mean", "value", period)
            used += r.n_used
            total += slots
            if r.value is not None:
                with_value += 1
                if exceedance(data, stack.stack_key, item, period).n_over:
                    over_stacks += 1
        rate = used / total * 100 if total else 0
        top = rank_stacks(data, item, "max", "value", period, TOP)
        names = ", ".join(
            f"{r.stack.business} 굴뚝 {r.stack.code} {format_value(r.value)} ppm" for r in top
        )
        lines.append(
            f"{label}: 값이 있는 굴뚝 {with_value}개, 정상 수신 {rate:.0f}%, "
            f"허용기준 초과가 있던 굴뚝 {over_stacks}개 / 최댓값 상위 {names or '없음'}"
        )
        numbers += [
            Number(
                name="max",
                pollutant=label,
                value=r.value,
                unit="ppm",
                n_used=r.n_used,
                n_excluded=r.n_excluded,
                n_missing=r.n_missing,
                period=period.label,
                as_of=as_of.isoformat() if as_of else None,
                subject=f"{r.stack.business} 굴뚝 {r.stack.code}",
                rank=i,
                stack_key=r.stack.stack_key,
            )
            for i, r in enumerate(top, 1)
        ]
    footer = f"{as_of:%Y-%m-%d %H:%M} 측정분 기준" if as_of else "기준 시각을 알 수 없음"
    return Part(
        part_id="p1",
        agent="report",
        status="DONE",
        label="요약",
        answer="\n".join([*lines, footer]),
        numbers=numbers,
        notice="정상 숫자 관측만으로 계산했고, 허용기준 초과는 법적 위반 여부를 판정하지 않습니다.",
    )
