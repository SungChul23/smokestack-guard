"""순위 방향(order)은 집계 방식(operation)과 따로다 (E2E 시험 결함 5).

"평균이 가장 낮은 굴뚝"은 집계가 평균이고 방향이 낮은 순이다. 예전에는 방향이 집계가 min일 때만
뒤집혀서 "평균이 가장 낮은"에 높은 순서로 답했다.
"""

from datetime import timedelta

import pytest
from conftest import DAY, make_data

from app.agent.compound import parse_plan
from app.agent.contract import ChatRequest
from app.agent.fold import fold
from app.agent.slots import Period, rank_order
from app.agent.tools import rank_stacks


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("어제 nox 평균이 가장 낮은 굴뚝 5곳", "asc"),
        ("평균이 제일 낮은 굴뚝", "asc"),
        ("nox 낮은 순서로 보여줘", "asc"),
        ("하위 3곳", "asc"),
        ("어제 nox 최솟값이 가장 높은 굴뚝", "desc"),
        ("평균이 가장 높은 굴뚝 5곳", "desc"),
        ("최댓값 상위 3곳", "desc"),
        ("높은 순서로", "desc"),
        ("어제 nox 평균 순위", None),  # 방향을 말하지 않았다
        ("높은 순서와 낮은 순서", None),  # 섞이면 정하지 않는다
        ("최저 기준을 알려줘", None),  # '최저'는 집계 말이지 방향이 아니다
    ],
)
def test_direction_is_read_separately_from_the_aggregate(text, expected):
    assert rank_order(fold(text)) == expected


def day() -> Period:
    return Period(DAY, DAY + timedelta(days=1), "2026-11-10 하루")


def keys(rows):
    return [r.stack.stack_key for r in rows]


def test_rank_sorts_by_the_given_direction_whatever_the_aggregate():
    data = make_data()  # NOx 하루 평균: 100:1 = 25.2, 302:1 = 20, 나머지 10(동률은 굴뚝 키 순)
    high = rank_stacks(data, "nox", "mean", "value", day(), 5, None, "desc")
    low = rank_stacks(data, "nox", "mean", "value", day(), 5, None, "asc")
    assert keys(high) == ["100:1", "302:1", "100:2", "200:3", "301:1"]
    assert keys(low) == ["100:2", "200:3", "301:1", "302:1", "100:1"]  # 평균인데 낮은 순
    assert [r.value for r in low] == sorted(r.value for r in low)


def test_without_a_direction_only_min_ranks_ascending_as_before():
    data = make_data()
    assert keys(rank_stacks(data, "nox", "mean", "value", day(), 1)) == ["100:1"]
    assert keys(rank_stacks(data, "nox", "max", "value", day(), 1)) == ["100:1"]
    ascending = rank_stacks(data, "nox", "min", "value", day(), 5)
    assert [r.value for r in ascending] == sorted(r.value for r in ascending)


def ask(service, message):
    return service.chat(ChatRequest(message=message, conversation_id="c-rank"), "u")


def test_lowest_average_question_answers_in_low_to_high_order(service):
    response = ask(service, "어제 NOx 평균이 가장 낮은 굴뚝 3곳 알려줘")
    assert response.status == "ANSWERED"
    part = response.parts[0]
    assert "낮은 순서" in part.answer and "높은 순서" not in part.answer
    values = [n.value for n in part.numbers]
    assert values == sorted(values) and len(values) == 3


def test_highest_average_question_still_answers_high_to_low(service):
    part = ask(service, "어제 NOx 평균이 가장 높은 굴뚝 3곳 알려줘").parts[0]
    assert "높은 순서" in part.answer
    values = [n.value for n in part.numbers]
    assert values == sorted(values, reverse=True)


def test_min_aggregate_with_a_high_direction_ranks_the_highest_minimum(service):
    part = ask(service, "어제 NOx 최솟값이 가장 높은 굴뚝 3곳 알려줘").parts[0]
    assert "높은 순서" in part.answer
    values = [n.value for n in part.numbers]
    assert values == sorted(values, reverse=True)


def test_plain_min_ranking_is_unchanged(service):
    part = ask(service, "어제 NOx 최솟값 낮은 순서 상위 3곳").parts[0]
    assert "낮은 순서" in part.answer


# ── 계획기(LLM) 경로 ──────────────────────────────────────────────────
def plan(item_extra=None, message="어제 NOx 평균이 가장 낮은 굴뚝 3곳"):
    item = {
        "id": "p1",
        "agent": "data",
        "intent": "rank",
        "pollutants": ["nox"],
        "time": {"kind": "yesterday"},
        "operation": "mean",
        "top_n": 3,
        **(item_extra or {}),
    }
    return parse_plan({"parts": [item]}, message)[0]


def test_planner_direction_is_kept_and_invalid_values_are_dropped():
    assert plan({"order": "asc"}).order == "asc"
    assert plan({"order": "desc"}, message="어제 NOx 평균 순위").order == "desc"
    assert plan({"order": "sideways"}, message="어제 NOx 평균 순위").order is None


def test_missing_direction_is_read_from_the_question_when_there_is_one_rank_part():
    assert plan().order == "asc"  # 계획기가 order를 빠뜨려도 질문 글에서 읽는다
    assert plan(message="어제 NOx 평균 순위 알려줘").order is None
