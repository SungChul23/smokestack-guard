"""질문 유형별 도구 실행과 답변 만들기. 문장은 템플릿이고 숫자는 도구가 계산한 값만 쓴다."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.agent.contract import Number, Part
from app.agent.slots import OPERATION_LABEL, POLLUTANT_LABEL, Command, Period
from app.agent.tools import (
    STATUS_LABEL,
    DataSource,
    aggregate_values,
    exceedance,
    extreme_time,
    gap_report,
    rank_stacks,
)
from app.agent.verify import format_value, verify_part

# 공개 API 지연(약 70분, 사용자 설명)보다 크게 벌어지면 최근 데이터가 안 들어왔을 수 있다고 알린다.
FRESHNESS_WARN = timedelta(hours=2)


def _reasons(label: str, counts: dict[int, int]) -> str:
    text = ", ".join(
        f"{STATUS_LABEL.get(code, '확인할 수 없는 상태')} {n}건"
        for code, n in sorted(counts.items())
    )
    return f"{label} 제외 사유: {text}" if text else ""


def _footer(as_of: datetime | None) -> str:
    return f"{as_of:%Y-%m-%d %H:%M} 측정분 기준" if as_of else "기준 시각을 알 수 없음"


def _checked(part: Part) -> tuple[Part, bool]:
    problems = verify_part(part)
    if not problems:
        return part, False
    failed = part.model_copy(
        update={
            "status": "UNAVAILABLE",
            "answer": None,
            "notice": "숫자 검증에 실패해 답변을 내지 않았습니다.",
        }
    )
    return failed, True


def run_aggregate(
    data: DataSource, command: Command, period: Period, as_of: datetime | None
) -> tuple[Part, bool]:
    stack_key = command["stack"]["stack_key"]  # type: ignore[index]
    info = data.get_stack(stack_key)
    operation, metric = command["operation"], command.get("metric") or "value"
    numbers: list[Number] = []
    lines: list[str] = []
    notes: list[str] = []
    for item in command["pollutants"]:
        result = aggregate_values(data, stack_key, item, operation, metric, period)
        label = POLLUTANT_LABEL[item]
        numbers.append(
            Number(
                name=operation,
                pollutant=label,
                value=result.value,
                unit=result.unit,
                n_used=result.n_used,
                n_excluded=result.n_excluded,
                n_missing=result.n_missing,
                period=period.label,
                as_of=as_of.isoformat() if as_of else None,
            )
        )
        if result.value is None:
            lines.append(
                f"{label}: 정상 숫자 관측이 없어 "
                f"{OPERATION_LABEL[operation]}을 계산하지 못했습니다."
            )
        else:
            lines.append(
                f"{label} {period.label} {OPERATION_LABEL[operation]} "
                f"{format_value(result.value)} {result.unit}"
                f" (사용 {result.n_used}건 · 상태 제외 {result.n_excluded}건"
                f" · 행 없음 {result.n_missing}건)"
            )
        if result.status_counts:
            notes.append(_reasons(label, result.status_counts))
    title = f"{info.business} 굴뚝 {info.code}" if info else stack_key
    done = any(n.value is not None for n in numbers)
    part = Part(
        part_id="p1",
        agent="data",
        status="DONE" if done else "UNAVAILABLE",
        label="현황",
        answer="\n".join([title, *lines, _footer(as_of)]),
        numbers=numbers,
        notice="\n".join(notes) or None,
    )
    return _checked(part)


def run_rank(
    data: DataSource, command: Command, period: Period, as_of: datetime | None
) -> tuple[Part, bool]:
    item = command["pollutants"][0]
    operation = command.get("operation") or "max"
    metric = command.get("metric") or "value"
    top_n = command["top_n"]
    label = POLLUTANT_LABEL[item]
    site_ids = set(command["site_ids"]) if command.get("site_ids") else None
    scope = f"{command['scope_label']} " if command.get("scope_label") else ""
    rows = rank_stacks(data, item, operation, metric, period, top_n, site_ids)
    if not rows:
        return Part(
            part_id="p1",
            agent="data",
            status="UNAVAILABLE",
            label="순위",
            notice=f"{period.label}에 정상 숫자 관측이 있는 굴뚝이 없어 순위를 만들지 못했습니다.",
        ), False
    unit = "%" if metric == "ratio" else "ppm"
    direction = "낮은" if operation == "min" else "높은"
    lines = [
        f"{scope}{label} {period.label} {OPERATION_LABEL[operation]} {direction} 순서 "
        f"상위 {len(rows)}곳"
    ]
    numbers: list[Number] = []
    for rank, row in enumerate(rows, start=1):
        subject = f"{row.stack.business} 굴뚝 {row.stack.code}"
        lines.append(f"{rank}. {subject} {format_value(row.value)} {unit} (사용 {row.n_used}건)")
        numbers.append(
            Number(
                name=operation,
                pollutant=label,
                value=row.value,
                unit=unit,
                n_used=row.n_used,
                n_excluded=row.n_excluded,
                n_missing=row.n_missing,
                period=period.label,
                as_of=as_of.isoformat() if as_of else None,
                subject=subject,
                rank=rank,
                stack_key=row.stack.stack_key,
            )
        )
    part = Part(
        part_id="p1",
        agent="data",
        status="DONE",
        label="순위",
        answer="\n".join([*lines, _footer(as_of)]),
        numbers=numbers,
        notice="정상 숫자 관측만으로 계산했고 상태 행(미수신·보수 중 등)은 뺐습니다.",
    )
    return _checked(part)


def _hhmm(t: datetime) -> str:
    return f"{t:%H:%M}"


def run_gap(
    data: DataSource, command: Command, period: Period, as_of: datetime | None
) -> tuple[Part, bool]:
    stack_key = command["stack"]["stack_key"]  # type: ignore[index]
    info = data.get_stack(stack_key)
    title = f"{info.business} 굴뚝 {info.code}" if info else stack_key
    lines: list[str] = [title]
    for item in command["pollutants"]:
        label = POLLUTANT_LABEL[item]
        report = gap_report(data, stack_key, item, period)
        if report.not_monitored:
            lines.append(
                f"{label}: 이 굴뚝은 {label}를 측정하지 않는 것으로 보입니다"
                "(값·기준값이 모두 없음)."
            )
            continue
        empty = report.expected - report.n_ok
        if empty == 0:
            lines.append(f"{label} {period.label}: 빠진 구간이 없습니다({report.expected}구간).")
            continue
        reasons = ", ".join(
            f"{STATUS_LABEL.get(code, '확인할 수 없는 상태')} {n}구간"
            for code, n in sorted(report.status_counts.items())
        )
        lines.append(
            f"{label} {period.label} {report.expected}구간 중 정상 {report.n_ok}구간, "
            f"비어 있는 구간 {empty}구간 ({reasons})"
        )
        for run in report.runs:
            span = _hhmm(run.start) if run.slots == 1 else f"{_hhmm(run.start)}~{_hhmm(run.end)}"
            cause = STATUS_LABEL.get(run.cause, "확인할 수 없는 상태")
            lines.append(f"  · 긴 공백: {span} {cause} {run.slots}구간 연속")
    part = Part(
        part_id="p1",
        agent="data",
        status="DONE",
        label="결측 이유",
        answer="\n".join([*lines, _footer(as_of)]),
        notice="상태 문구는 API 원문 상태를 옮긴 것이며 원인을 추정하지 않았습니다.",
    )
    return part, False


def run_freshness(data: DataSource, now: datetime) -> Part:
    as_of = data.as_of()
    if as_of is None:
        return Part(
            part_id="p1",
            agent="data",
            status="UNAVAILABLE",
            label="데이터 기준",
            notice="데이터의 기준 시각을 알 수 없습니다.",
        )
    lines = [f"데이터는 {as_of:%Y-%m-%d %H:%M} 측정분까지 들어 있습니다."]
    behind = now - as_of
    notice = None
    if behind > FRESHNESS_WARN:
        hours = int(behind.total_seconds() // 3600)
        notice = (
            f"현재 시각과 약 {hours}시간 이상 차이가 납니다. "
            "최근 측정분이 아직 들어오지 않았을 수 있습니다."
        )
    return Part(
        part_id="p1",
        agent="data",
        status="DONE",
        label="데이터 기준",
        answer="\n".join(lines),
        notice=notice,
    )


def _title(data: DataSource, stack_key: str) -> str:
    info = data.get_stack(stack_key)
    return f"{info.business} 굴뚝 {info.code}" if info else stack_key


def run_exceedance(
    data: DataSource, stack_key: str, item: str, period: Period, as_of: datetime | None
) -> Part:
    label = POLLUTANT_LABEL[item]
    r = exceedance(data, stack_key, item, period)
    lines = [_title(data, stack_key)]
    numbers: list[Number] = []
    if r.n_used == 0:
        lines.append(f"{label}: 허용기준과 비교할 정상 관측이 없어 계산하지 못했습니다.")
        status = "UNAVAILABLE"
    else:
        lines.append(
            f"{label} {period.label} 허용기준 초과 {r.n_over}회 "
            f"(30분 값 기준 약 {r.n_over * 0.5:g}시간, 비교한 관측 {r.n_used}건)"
        )
        if r.limit_min is not None:
            span = f"{r.limit_min:g}"
            if r.limit_max != r.limit_min:
                span += f"~{r.limit_max:g}"
            lines.append(f"적용 허용기준: {span} ppm")
        if r.longest_run and r.run_start and r.run_end:
            lines.append(
                f"가장 길게 이어진 초과: {r.run_start:%H:%M}~{r.run_end:%H:%M} "
                f"({r.longest_run}회 연속)"
            )
        if r.n_no_limit:
            lines.append(f"기준값이 없어 비교하지 못한 관측 {r.n_no_limit}건은 뺐습니다.")
        status = "DONE"
        numbers.append(
            Number(
                name="exceed_count",
                pollutant=label,
                value=float(r.n_over),
                unit="회",
                n_used=r.n_used,
                n_excluded=0,
                n_missing=0,
                period=period.label,
                as_of=as_of.isoformat() if as_of else None,
            )
        )
    part = Part(
        part_id="p1",
        agent="data",
        status=status,  # type: ignore[arg-type]
        label="초과 횟수",
        answer="\n".join([*lines, _footer(as_of)]),
        numbers=numbers,
        notice="측정값과 자료에 실린 허용기준을 비교한 값이며, 법적 위반 여부를 판정하지 않습니다.",
    )
    return _checked(part)[0]


def run_extreme_time(
    data: DataSource,
    stack_key: str,
    item: str,
    operation: str,
    period: Period,
    as_of: datetime | None,
) -> Part:
    label = POLLUTANT_LABEL[item]
    found = extreme_time(data, stack_key, item, operation, period)
    lines = [_title(data, stack_key)]
    numbers: list[Number] = []
    if found is None:
        lines.append(f"{label}: 정상 숫자 관측이 없어 시각을 찾지 못했습니다.")
        status = "UNAVAILABLE"
    else:
        value, at = found
        word = "최솟값" if operation == "min" else "최댓값"
        lines.append(f"{label} {period.label} {word} {format_value(value)} ppm, {at:%H:%M} 측정분")
        numbers.append(
            Number(
                name=operation,
                pollutant=label,
                value=value,
                unit="ppm",
                n_used=0,
                n_excluded=0,
                n_missing=0,
                period=period.label,
                as_of=as_of.isoformat() if as_of else None,
            )
        )
        status = "DONE"
    part = Part(
        part_id="p1",
        agent="data",
        status=status,  # type: ignore[arg-type]
        label="극값 시각",
        answer="\n".join([*lines, _footer(as_of)]),
        numbers=numbers,
        notice="정상 숫자 관측만으로 찾았고 상태 행은 뺐습니다.",
    )
    return _checked(part)[0]


def _unavailable(label: str, notice: str) -> Part:
    return Part(part_id="p1", agent="data", status="UNAVAILABLE", label=label, notice=notice)


def run_diff(first: Part, second: Part) -> Part:
    """이미 계산한 두 값을 견준다(새 조회 없음). 같은 물질·단위일 때만 계산한다."""
    a = first.numbers[0] if first.numbers else None
    b = second.numbers[0] if second.numbers else None
    if a is None or b is None or a.value is None or b.value is None:
        return _unavailable("차이", "견줄 두 값이 모두 있어야 차이를 계산합니다.")
    if a.pollutant != b.pollutant or a.unit != b.unit:
        return _unavailable("차이", "물질이나 단위가 달라 차이를 계산하지 않습니다.")
    diff = b.value - a.value
    pct = f" ({diff / a.value * 100:+.1f}%)" if a.value else ""
    sign = "+" if diff > 0 else ""
    name_a = (first.answer or "").split("\n")[0] or "앞 값"
    name_b = (second.answer or "").split("\n")[0] or "뒤 값"
    answer = "\n".join(
        [
            f"{a.pollutant} 값 비교",
            f"{name_a} {a.period}: {format_value(a.value)} {a.unit}",
            f"{name_b} {b.period}: {format_value(b.value)} {b.unit}",
            f"차이(뒤 − 앞): {sign}{format_value(diff)} {a.unit}{pct}",
        ]
    )
    part = Part(
        part_id="p1",
        agent="data",
        status="DONE",
        label="차이",
        answer=answer,
        numbers=[
            Number(
                name="diff",
                pollutant=a.pollutant,
                value=diff,
                unit=a.unit,
                n_used=0,
                n_excluded=0,
                n_missing=0,
                period=f"{a.period} → {b.period}",
                as_of=a.as_of,
            )
        ],
        notice="이미 조회한 두 값으로 계산했습니다.",
    )
    return _checked(part)[0]


def run_site_stacks(
    data: DataSource,
    site_id: str,
    item: str,
    operation: str,
    metric: str,
    period: Period,
    as_of: datetime | None,
) -> Part:
    """사업장의 굴뚝 전부를 굴뚝별로 나란히 보여 준다(합치거나 평균 내지 않는다)."""
    stacks = sorted(
        (s for s in data.list_stacks() if s.site_id == site_id),
        key=lambda s: (len(s.code), s.code),
    )
    label = POLLUTANT_LABEL[item]
    unit = "%" if metric == "ratio" else "ppm"
    lines = [
        f"{stacks[0].business if stacks else site_id} 굴뚝 {len(stacks)}개 — "
        f"{label} {period.label} {OPERATION_LABEL[operation]}(굴뚝별)"
    ]
    numbers: list[Number] = []
    for stack in stacks:
        r = aggregate_values(data, stack.stack_key, item, operation, metric, period)
        if r.value is None:
            why = _reasons("", r.status_counts).replace(" 제외 사유: ", "") or "정상 관측 없음"
            lines.append(f"- 굴뚝 {stack.code}: 값 없음 ({why})")
            continue
        shown = format_value(r.value)
        lines.append(
            f"- 굴뚝 {stack.code}: {shown} {unit} (사용 {r.n_used}건 · 제외 {r.n_excluded}건)"
        )
        numbers.append(
            Number(
                name=operation,
                pollutant=label,
                value=r.value,
                unit=unit,
                n_used=r.n_used,
                n_excluded=r.n_excluded,
                n_missing=r.n_missing,
                period=period.label,
                as_of=as_of.isoformat() if as_of else None,
                subject=f"{stack.business} 굴뚝 {stack.code}",
                stack_key=stack.stack_key,
            )
        )
    part = Part(
        part_id="p1",
        agent="data",
        status="DONE" if numbers else "UNAVAILABLE",
        label="굴뚝별",
        answer="\n".join([*lines, _footer(as_of)]),
        numbers=numbers,
        notice="굴뚝마다 기준과 측정 대상이 달라 하나의 값으로 합치지 않고 굴뚝별로 보여 줍니다.",
    )
    return _checked(part)[0]
