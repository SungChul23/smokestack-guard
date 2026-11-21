"""질문 유형 시험: 전국 순위, 데이터 기준 시각, 데이터가 비는 이유."""

import pytest

from app.agent.contract import ChatRequest

USER = "user-a"


def ask(service, message, conversation_id=None):
    return service.chat(ChatRequest(message=message, conversation_id=conversation_id), USER)


def pick(service, response, option_id):
    return service.chat(
        ChatRequest(
            conversation_id=response.conversation_id,
            resume={"card_id": response.card.card_id, "option_id": option_id},
        ),
        USER,
    )


# ── 전국 순위 ─────────────────────────────────────────────────────────
def test_rank_orders_by_max_and_breaks_ties_by_key(service):
    response = ask(service, "어제 전국에서 NOx 가장 높았던 굴뚝 상위 3")
    assert response.status == "ANSWERED"
    part = response.parts[0]
    assert part.label == "순위" and part.agent == "data"
    values = [(n.rank, n.subject, n.value) for n in part.numbers]
    assert values == [
        (1, "㈜가나에너지 굴뚝 1", 47.0),
        (2, "동서식품(주) 굴뚝 1", 20.0),  # 302:1
        (3, "㈜가나에너지 굴뚝 2", 10.0),  # 같은 값은 굴뚝 키 순서(100:2)
    ]
    assert "1. ㈜가나에너지 굴뚝 1 47.00 ppm" in part.answer
    assert response.data_as_of == "2026-11-10T23:30:00+09:00"


def test_rank_by_mean_and_lowest(service):
    mean = ask(service, "어제 NOx 평균이 가장 높은 굴뚝 상위 1")
    assert mean.parts[0].numbers[0].value == pytest.approx(1109 / 44)
    low = ask(service, "어제 NOx 가장 낮은 굴뚝 상위 2")
    assert [n.value for n in low.parts[0].numbers] == [0.0, 10.0]


def test_rank_defaults_to_five_and_caps_at_ten(service):
    five = ask(service, "어제 NOx 가장 높았던 굴뚝")
    assert len(five.parts[0].numbers) == 5
    capped = ask(service, "어제 NOx 가장 높았던 굴뚝 상위 50")
    assert len(capped.parts[0].numbers) <= 10


def test_rank_excludes_stacks_without_numeric_values(service):
    response = ask(service, "어제 SOx 가장 높았던 굴뚝")
    # SOx는 100:1만 있고 측정하지 않는 물질(상태 8)이라 순위가 없다.
    part = response.parts[0]
    assert part.status == "UNAVAILABLE" and part.numbers == []
    assert "순위를 만들지 못했습니다" in part.notice


def test_rank_asks_for_one_pollutant_and_the_period(service):
    both = ask(service, "어제 NOx SOx 가장 높았던 굴뚝")
    assert both.card.kind == "POLLUTANT"
    assert [o.label for o in both.card.options] == ["NOx", "SOx", "이 부분은 빼고 진행"]
    answered = pick(service, both, "nox")
    assert answered.status == "ANSWERED"
    no_time = ask(service, "NOx 가장 높았던 굴뚝")
    assert no_time.card.kind == "TIME"
    assert pick(service, no_time, "yesterday").status == "ANSWERED"


def test_rank_followup_keeps_the_rank_type(service):
    first = ask(service, "어제 NOx 가장 높았던 굴뚝 상위 2")
    follow = ask(service, "그럼 SOx는?", first.conversation_id)
    # SOx는 순위를 만들 값이 없지만, 유형은 순위로 이어진다.
    assert follow.parts[0].label == "순위" and follow.parts[0].status == "UNAVAILABLE"


# ── 데이터 기준 시각 ──────────────────────────────────────────────────
def test_freshness_states_the_measurement_time_not_the_word_latest(service):
    response = ask(service, "데이터가 언제 기준이야?")
    part = response.parts[0]
    assert response.status == "ANSWERED" and part.label == "데이터 기준"
    assert "2026-11-10 23:30 측정분까지" in part.answer
    assert "최신" not in part.answer
    # 시계가 2026-11-11 09:00이라 9시간 이상 벌어져 알린다.
    assert "이상 차이" in part.notice
    assert response.data_as_of == "2026-11-10T23:30:00+09:00"


def test_freshness_has_no_warning_when_recent(service, clock):
    from datetime import timedelta

    clock.now = clock.now.replace(day=10, hour=23, minute=50) + timedelta(minutes=0)
    response = ask(service, "마지막 측정 시각이 언제야")
    assert response.parts[0].notice is None


# ── 데이터가 비는 이유 ────────────────────────────────────────────────
def test_gap_explains_causes_and_longest_runs(service):
    response = ask(service, "가나에너지 굴뚝 1 어제 NOx 데이터가 왜 비어 있어?")
    part = response.parts[0]
    assert response.status == "ANSWERED" and part.label == "결측 이유"
    assert "48구간 중 정상 44구간, 비어 있는 구간 4구간" in part.answer
    assert "미수신 2구간" in part.answer and "보수 중 1구간" in part.answer
    assert "수신 기록 없음 1구간" in part.answer
    assert "01:00~01:30 미수신 2구간 연속" in part.answer
    assert "원인을 추정하지 않았습니다" in part.notice


def test_gap_for_a_pollutant_the_stack_does_not_measure(service):
    response = ask(service, "가나에너지 굴뚝 1 어제 SOx 비어 있는 이유")
    assert "측정하지 않는 것으로 보입니다" in response.parts[0].answer


def test_gap_without_conditions_inherits_the_previous_question(service):
    first = ask(service, "가나에너지 굴뚝 1 어제 NOx 평균")
    gap = ask(service, "왜 비어 있어?", first.conversation_id)
    assert gap.parts[0].label == "결측 이유"
    assert "정상 44구간" in gap.parts[0].answer


def test_gap_without_any_context_asks_for_the_stack(service):
    response = ask(service, "왜 비어 있어?")
    assert response.status == "REFUSED"
    assert any("굴뚝" in n for n in response.notices)


def test_conditions_survive_a_value_that_is_unavailable(service):
    first = ask(service, "가나에너지 굴뚝 1 어제 NOx 평균")
    sox = ask(service, "그럼 SOx는?", first.conversation_id)
    assert sox.parts[0].status == "UNAVAILABLE"
    # 값이 비었어도 굴뚝·기간·집계는 이어진다.
    back = ask(service, "그럼 NOx는?", first.conversation_id)
    assert back.parts[0].status == "DONE"
    assert back.parts[0].numbers[0].value == pytest.approx(1109 / 44)
