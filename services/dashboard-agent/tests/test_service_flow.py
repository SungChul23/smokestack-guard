"""질문 → 판정 → 카드(중단·재개) → 도구 → 응답 흐름 시험."""

from datetime import timedelta

import pytest

from app.agent.contract import ChatRequest

USER = "user-a"


def ask(service, message, conversation_id=None, **extra):
    return service.chat(
        ChatRequest(message=message, conversation_id=conversation_id, **extra), USER
    )


def pick(service, response, option_id, user=USER):
    return service.chat(
        ChatRequest(
            conversation_id=response.conversation_id,
            resume={"card_id": response.card.card_id, "option_id": option_id},
        ),
        user,
    )


def test_complete_question_is_answered_with_structured_numbers(service):
    response = ask(service, "가나에너지 굴뚝 1 어제 NOx 평균 알려줘")
    assert response.status == "ANSWERED" and response.card is None
    assert response.data_as_of == "2026-11-10T23:30:00+09:00"
    part = response.parts[0]
    assert part.agent == "data" and part.status == "DONE" and part.label == "현황"
    number = part.numbers[0]
    assert number.value == pytest.approx(1109 / 44)
    assert (number.n_used, number.n_excluded, number.n_missing) == (44, 3, 1)
    assert "25.20" in part.answer and "2026-11-10 23:30 측정분 기준" in part.answer
    assert "미수신 2건" in part.notice and "보수 중 1건" in part.notice
    assert response.trace.turn_type == "MESSAGE"


def test_missing_period_asks_a_card_then_resume_answers(service):
    first = ask(service, "가나에너지 굴뚝 1 NOx 평균")
    assert first.status == "NEEDS_INPUT" and first.card.kind == "TIME"
    labels = [o.label for o in first.card.options]
    assert labels == ["어제", "오늘 현재까지", "이 부분은 빼고 진행"]
    assert first.card.options[-1].skip_part is True
    second = pick(service, first, "yesterday")
    assert second.status == "ANSWERED" and second.trace.turn_type == "RESUME"
    assert second.parts[0].numbers[0].value == pytest.approx(1109 / 44)


def test_skip_option_ends_without_running(service):
    first = ask(service, "가나에너지 굴뚝 1 NOx 평균")
    second = pick(service, first, "skip")
    assert second.status == "REFUSED"
    assert second.parts[0].status == "SKIPPED" and second.parts[0].numbers == []


def test_missing_operation_and_pollutant_are_asked_in_order(service):
    first = ask(service, "가나에너지 굴뚝 1 어제")
    assert first.card.kind == "POLLUTANT"
    second = pick(service, first, "nox")
    assert second.card.kind == "OPERATION"
    third = pick(service, second, "max")
    assert third.status == "ANSWERED" and third.parts[0].numbers[0].value == 47


def test_business_with_several_stacks_asks_the_code(service):
    first = ask(service, "가나에너지 어제 NOx 평균")
    assert first.card.kind == "STACK_CODE"
    labels = [o.label for o in first.card.options]
    assert labels == ["굴뚝 1", "굴뚝 2", "이 중에 없음", "이 부분은 빼고 진행"]
    second = pick(service, first, "100:2")
    assert second.status == "ANSWERED" and second.parts[0].numbers[0].value == 10


def test_same_name_in_two_sites_asks_which_site(service):
    first = ask(service, "동서식품 굴뚝 1 어제 NOx 평균")
    assert first.card.kind == "STACK_CANDIDATES"
    assert [o.label for o in first.card.options][:2] == [
        "동서식품(주) · 충청북도",
        "동서식품(주) · 인천광역시",
    ]
    second = pick(service, first, "302")
    assert second.status == "ANSWERED" and second.parts[0].numbers[0].value == 20


def test_none_of_these_asks_to_retype(service):
    first = ask(service, "가나에너지 어제 NOx 평균")
    second = pick(service, first, "none")
    assert second.status == "REFUSED"
    assert any("다시 말씀" in n for n in second.notices)


def test_retyped_name_completes_the_question_with_the_same_conditions(service):
    first = ask(service, "가나에너지 어제 NOx 평균")
    second = pick(service, first, "none")
    third = ask(service, "다라화학", second.conversation_id)
    assert third.status == "ANSWERED"
    assert third.parts[0].numbers[0].value == 10  # 어제 NOx 평균 조건을 이어받았다


def test_a_new_question_is_not_read_as_a_retyped_name(service):
    first = ask(service, "가나에너지 어제 NOx 평균")
    second = pick(service, first, "none")
    third = ask(service, "다라화학 굴뚝 3 어제 SOx 최대", second.conversation_id)
    assert third.status != "REFUSED" or not any("다시 말씀" in n for n in third.notices)


def test_after_two_failures_in_a_row_the_map_is_suggested(service):
    first = ask(service, "가나에너지 어제 NOx 평균")
    second = pick(service, first, "none")  # 첫 번째 실패
    third = ask(service, "없는이름의회사", second.conversation_id)  # 두 번째 실패
    assert any("지도" in n for n in third.notices)
    # 지도 안내 뒤에는 이름 대기가 끝난다: 이름만 말하면 새 질문으로 처리된다
    fourth = ask(service, "다라화학", second.conversation_id)
    assert not any("앞서 말씀하신 조건" in n for n in fourth.notices)


def test_followup_inherits_conditions_and_reads_fresh(service):
    ask(service, "가나에너지 굴뚝 1 어제 NOx 평균")
    follow = ask(service, "그럼 SOx는?", conversation_id=None)
    # 새 대화라 이어받을 조건이 없다.
    assert follow.status == "REFUSED"


def test_followup_in_the_same_conversation(service):
    first = ask(service, "가나에너지 굴뚝 1 어제 NOx 평균")
    follow = ask(service, "그럼 SOx는?", first.conversation_id)
    part = follow.parts[0]
    # 굴뚝 1은 SOx를 측정하지 않는다(상태 8). 굴뚝·기간·집계는 이어받았다.
    assert part.status == "UNAVAILABLE" and part.numbers[0].pollutant == "SOx"
    assert part.numbers[0].period == "2026-11-10 하루" and part.numbers[0].name == "mean"
    assert "측정하지 않는 물질 48건" in part.notice


def test_followup_expires_after_15_minutes(service, clock):
    first = ask(service, "가나에너지 굴뚝 1 어제 NOx 평균")
    clock.now += timedelta(minutes=16)
    follow = ask(service, "그럼 SOx는?", first.conversation_id)
    assert follow.status == "REFUSED"
    assert any("굴뚝 번호" in n for n in follow.notices)


def test_out_of_scope_question_is_refused(service):
    response = ask(service, "오늘 날씨 어때")
    assert response.status == "REFUSED" and response.parts == []
    assert any("지원하지 않습니다" in n for n in response.notices)


def test_unknown_business_is_not_invented(service):
    response = ask(service, "없는회사 굴뚝 1 어제 NOx 평균")
    # 알려진 사업장 이름이 없어 굴뚝을 특정하지 못한다.
    assert response.status == "REFUSED" and response.parts == []


def test_selected_stack_fills_a_missing_stack(service):
    response = ask(service, "어제 NOx 평균", context={"selectedStackId": "100:1"})
    assert response.status == "ANSWERED"
    assert response.parts[0].numbers[0].value == pytest.approx(1109 / 44)


def test_unsupported_period_is_not_guessed_but_asked(service):
    first = ask(service, "가나에너지 굴뚝 1 지난 200시간 NOx 평균")
    assert first.status == "NEEDS_INPUT" and first.card.kind == "PERIOD" and first.parts == []
    assert "아직 지원하지 않습니다" in first.card.message
    assert pick(service, first, "yesterday").status == "ANSWERED"


def test_unsupported_operation_word_is_named_in_the_single_flow_card(service):
    first = ask(service, "가나에너지 굴뚝 1 어제 NOx 중앙값")
    assert (
        first.card.kind == "OPERATION"
        and "'중앙값'은(는) 아직 지원하지 않습니다" in first.card.message
    )


def test_a_region_word_asks_what_to_see_instead_of_picking_a_site(service):
    first = ask(service, "경기 어제 NOx 평균")
    assert first.status == "NEEDS_INPUT" and first.card.kind == "SCOPE"
    assert "지역·묶음으로 보입니다" in first.card.message


def test_stale_card_is_refused(service):
    first = ask(service, "가나에너지 굴뚝 1 NOx 평균")
    stale = service.chat(
        ChatRequest(
            conversation_id=first.conversation_id,
            resume={"card_id": "not-this-card", "option_id": "yesterday"},
        ),
        USER,
    )
    assert stale.status == "REFUSED" and "만료" in stale.notices[0]
    # 진짜 카드는 아직 유효하다.
    assert pick(service, first, "yesterday").status == "ANSWERED"


def test_new_question_closes_the_pending_card(service):
    first = ask(service, "가나에너지 굴뚝 1 NOx 평균")
    answered = ask(service, "가나에너지 굴뚝 2 어제 NOx 평균", first.conversation_id)
    assert answered.status == "ANSWERED"
    late = pick(service, first, "yesterday")
    assert late.status == "REFUSED" and "만료" in late.notices[0]


def test_another_user_cannot_resume_my_card(service):
    first = ask(service, "가나에너지 굴뚝 1 NOx 평균")
    other = service.chat(
        ChatRequest(
            conversation_id=first.conversation_id,
            resume={"card_id": first.card.card_id, "option_id": "yesterday"},
        ),
        "user-b",
    )
    assert other.status == "REFUSED" and "만료" in other.notices[0]


def test_same_request_id_is_not_processed_twice(service, extractor):
    request = ChatRequest(message="가나에너지 굴뚝 1 어제 NOx 평균", request_id="req-1")
    first = service.chat(request, USER)
    again = service.chat(request, USER)
    assert extractor.calls == 1
    assert again.parts[0].numbers == first.parts[0].numbers
    assert again.request_id == first.request_id == "req-1"


# ── 지역 → 사업장 → 굴뚝 ──────────────────────────────────────────────
def test_region_word_settles_a_name_shared_by_two_sites(service):
    chungbuk = ask(service, "충북 동서식품 굴뚝 1 어제 NOx 평균")
    assert chungbuk.status == "ANSWERED" and chungbuk.parts[0].numbers[0].value == 10
    incheon = ask(service, "인천 동서식품 굴뚝 1 어제 NOx 평균")
    assert incheon.status == "ANSWERED" and incheon.parts[0].numbers[0].value == 20


def test_a_bare_number_that_is_a_real_stack_code_is_used(service):
    response = ask(service, "가나에너지 2 어제 NOx 평균")
    assert response.status == "ANSWERED"
    assert "굴뚝 2" in response.parts[0].answer


def test_a_bare_number_that_is_not_a_stack_code_is_asked(service):
    response = ask(service, "가나에너지 7 어제 NOx 평균")
    assert response.card.kind == "STACK_CODE"


def test_a_missing_stack_code_asks_with_a_clear_message(service):
    response = ask(service, "가나에너지 굴뚝 9 어제 NOx 평균")
    assert (
        response.card.kind == "STACK_CODE" and "그 번호의 굴뚝이 없습니다" in response.card.message
    )
    answered = pick(service, response, "100:2")
    assert answered.status == "ANSWERED"
