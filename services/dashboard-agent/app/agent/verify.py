"""출력 검증(숫자 대조). 답변 문장의 숫자가 도구가 계산한 구조화 값과 같은지 확인한다."""

from __future__ import annotations

from app.agent.contract import Number, Part


def format_value(value: float) -> str:
    return f"{value:,.2f}"


def verify_part(part: Part) -> list[str]:
    """어긋난 항목 설명을 돌려준다. 비어 있으면 통과다."""
    problems: list[str] = []
    answer = part.answer or ""
    for number in part.numbers:
        if number.value is None:
            continue
        count = number.name.endswith("count")
        shown = str(int(number.value)) if count else format_value(number.value)
        if shown not in answer:
            problems.append(f"{number.pollutant} {number.name} 값이 답변 문장에 없다")
    return problems


def numbers_consistent(numbers: list[Number]) -> bool:
    return all(n.n_used >= 0 and n.n_excluded >= 0 and n.n_missing >= 0 for n in numbers)
