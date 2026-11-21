"""복합 질문의 되묻기 카드: 모호한 부분은 AI가 채우지 않고 사람에게 묻고, 답하면 이어서 처리한다."""

from conftest import make_data
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.contract import ChatRequest
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import SiteResolver
from app.agent.service import AgentService


class FakePlanner:
    def __init__(self, raw):
        self.raw = raw

    def plan(self, message, now, *, has_last, last=None):
        return self.raw


def part(id_, agent="data", intent="aggregate", **kw):
    return {"id": id_, "agent": agent, "intent": intent, **kw}


def service(clock, raw):
    data = make_data()
    resolver = SiteResolver(sites_from(data))
    return AgentService(
        RuleExtractor(resolver),
        data,
        InMemorySaver(),
        clock,
        "rule-dev",
        resolver,
        FakePlanner(raw),
    )


def ask(svc, message, **extra):
    return svc.chat(ChatRequest(message=message, **extra), "u")


def pick(svc, response, option_id):
    return svc.chat(
        ChatRequest(
            conversation_id=response.conversation_id,
            resume={"card_id": response.card.card_id, "option_id": option_id},
        ),
        "u",
    )


NOX_YDAY = {"pollutants": ["nox"], "time": {"kind": "yesterday"}, "operation": "mean"}


def test_missing_period_is_asked_then_answered(clock):
    raw = {
        "parts": [
            part("p1", stack={"business": "가나에너지", "code": "1"}, **NOX_YDAY, note="평균"),
            part(
                "p2",
                stack={"business": "가나에너지", "code": "1"},
                pollutants=["nox"],
                operation="max",
                note="최댓값",
            ),
        ]
    }
    svc = service(clock, raw)
    first = ask(svc, "가나에너지 굴뚝 1 어제 NOx 평균이랑 최댓값")
    assert first.status == "NEEDS_INPUT" and first.card.kind == "TIME"
    assert first.card.message.startswith("[최댓값]")  # 어느 부분을 묻는지 알려 준다
    done = pick(svc, first, "yesterday")
    assert done.status == "ANSWERED" and [p.status for p in done.parts] == ["DONE", "DONE"]


def test_region_word_is_not_guessed_as_a_site(clock):
    raw = {"parts": [part("p1", stack={"business": "충북"}, **NOX_YDAY, note="충북 평균")]}
    svc = service(clock, raw)
    first = ask(svc, "충북 어제 NOx 평균이랑 비교")
    assert first.card.kind == "SCOPE"
    labels = [o.label for o in first.card.options]
    assert "전국 순위로 보기" in labels and "이 부분은 빼고 진행" in labels
    assert any(
        "동서식품" in label for label in labels
    )  # 그 지역에 사업장이 적으면 직접 고르게 한다
    assert "지역·묶음으로 보입니다" in first.card.message
    chosen = pick(
        svc, first, "301"
    )  # 사업장을 고르면 굴뚝 번호를 다시 묻는 대신 단일 굴뚝은 바로 실행
    assert chosen.status == "ANSWERED" and chosen.parts[0].status == "DONE"


def test_region_can_be_turned_into_a_national_rank(clock):
    raw = {"parts": [part("p1", stack={"business": "충북"}, **NOX_YDAY, note="충북")]}
    svc = service(clock, raw)
    first = ask(svc, "충북 어제 NOx 평균이랑 비교")
    done = pick(svc, first, "national-rank")
    assert done.status == "ANSWERED" and "순서" in (done.parts[0].answer or "")


def test_all_stacks_lists_every_stack_of_the_site_side_by_side(clock):
    raw = {"parts": [part("p1", stack={"business": "가나에너지", "code": "all"}, **NOX_YDAY)]}
    response = ask(service(clock, raw), "가나에너지 굴뚝 전부 어제 NOx 평균이랑 비교")
    assert response.card is None and response.status == "ANSWERED"
    answer = response.parts[0].answer
    assert "굴뚝 2개" in answer and "굴뚝 1:" in answer and "굴뚝 2:" in answer
    assert len(response.parts[0].numbers) == 2 and "합치지 않고" in response.parts[0].notice


def test_unsupported_period_offers_supported_choices(clock):
    raw = {
        "parts": [
            part(
                "p1",
                stack={"business": "가나에너지", "code": "1"},
                pollutants=["nox"],
                time={"kind": "other"},
                operation="mean",
            )
        ]
    }
    svc = service(clock, raw)
    first = ask(svc, "가나에너지 굴뚝 1 지난주 NOx 평균이랑 최댓값")
    assert first.card.kind == "PERIOD"
    assert {o.id for o in first.card.options} >= {"yesterday", "today", "hours-24", "skip"}
    assert pick(svc, first, "yesterday").status == "ANSWERED"


def test_skip_option_leaves_the_part_out_and_answers_the_rest(clock):
    raw = {
        "parts": [
            part("p1", stack={"business": "가나에너지", "code": "1"}, **NOX_YDAY),
            part("p2", stack={"business": "충북"}, **NOX_YDAY),
        ]
    }
    svc = service(clock, raw)
    first = ask(svc, "가나에너지 굴뚝 1 어제 NOx 평균이랑 충북 평균 비교")
    assert first.card.kind == "SCOPE"
    done = pick(svc, first, "skip")
    assert done.status == "PARTIAL"
    assert [p.status for p in done.parts] == ["DONE", "SKIPPED"]


def test_a_value_the_planner_was_unsure_of_is_asked_even_if_filled(clock):
    raw = {
        "parts": [
            part(
                "p1",
                stack={"business": "가나에너지", "code": "1"},
                pollutants=["nox"],
                time={"kind": "yesterday"},
                operation="mean",
                unclear=["pollutants"],
            ),
            part("p2", agent="evidence", intent="law", note="법 기준"),
        ]
    }
    svc = service(clock, raw)
    first = ask(svc, "가나에너지 굴뚝 1 어제 NOx 평균 알려주고 법 기준도")
    assert first.card.kind == "POLLUTANT"
    done = pick(svc, first, "sox")
    assert done.parts[0].numbers[0].pollutant == "SOx"


def test_duplicate_site_names_ask_which_site(clock):
    raw = {"parts": [part("p1", stack={"business": "동서식품", "code": "1"}, **NOX_YDAY)]}
    svc = service(clock, raw)
    first = ask(svc, "동서식품 굴뚝 1 어제 NOx 평균이랑 비교")
    assert first.card.kind == "STACK_CANDIDATES"
    done = pick(svc, first, "302")
    assert done.status == "ANSWERED" and done.parts[0].numbers[0].value == 20


def test_map_selected_stack_fills_a_part_without_asking(clock):
    raw = {
        "parts": [part("p1", **NOX_YDAY, note="평균"), part("p2", agent="evidence", intent="law")]
    }
    svc = service(clock, raw)
    response = ask(svc, "어제 NOx 평균 알려주고 법 기준도", context={"selectedStackId": "100:1"})
    assert response.card is None and response.parts[0].status == "DONE"


def test_region_card_explains_why_an_average_would_mislead_with_real_numbers(clock):
    raw = {"parts": [part("p1", stack={"business": "경기"}, **NOX_YDAY, note="경기 평균")]}
    svc = service(clock, raw)
    first = ask(svc, "경기 어제 NOx 평균이랑 비교")
    message = first.card.message
    assert first.card.kind == "SCOPE"
    assert "지역 평균을 내면 원하는 값과 다를 수 있습니다" in message
    assert "허용기준이 달라(100~200 ppm, 2종)" in message  # 도구가 계산한 값
    assert "region-rank" in [o.id for o in first.card.options]


def test_region_rank_option_ranks_only_inside_the_region(clock):
    raw = {"parts": [part("p1", stack={"business": "경기"}, **NOX_YDAY)]}
    svc = service(clock, raw)
    first = ask(svc, "경기 어제 NOx 평균이랑 비교")
    done = pick(svc, first, "region-rank")
    assert done.status == "ANSWERED"
    answer = done.parts[0].answer or ""
    assert "경기 안에서" in answer and "가나에너지" in answer and "동서식품" not in answer


def test_a_group_word_that_reaches_execution_gets_an_explanation_not_a_bare_refusal(clock):
    from conftest import make_data

    from app.agent.compound import parse_plan, run_plan
    from app.agent.graph import sites_from
    from app.agent.names import SiteResolver

    data = make_data()
    parts = parse_plan(
        {"parts": [part("p1", stack={"business": "경기"}, **NOX_YDAY)]}, "경기 어제 NOx 평균"
    )
    out = run_plan(parts, data, SiteResolver(sites_from(data)), clock())
    assert out[0].status == "UNAVAILABLE" and "지역·묶음" in (out[0].notice or "")


def test_a_region_word_with_a_stack_number_is_a_stack_not_a_group(clock):
    raw = {"parts": [part("p1", stack={"business": "충북", "code": "1"}, **NOX_YDAY)]}
    first = ask(service(clock, raw), "충북 1번 굴뚝 어제 NOx 평균이랑 비교")
    assert first.card is None or first.card.kind != "SCOPE"


def test_unsupported_operation_word_is_named_in_the_card(clock):
    raw = {
        "parts": [
            part(
                "p1",
                stack={"business": "가나에너지", "code": "1"},
                pollutants=["nox"],
                time={"kind": "yesterday"},
            )
        ]
    }
    first = ask(service(clock, raw), "가나에너지 굴뚝 1 어제 NOx 중앙값이랑 비교")
    assert (
        first.card.kind == "OPERATION"
        and "'중앙값'은(는) 아직 지원하지 않습니다" in first.card.message
    )


def test_derived_calculation_is_named_and_the_user_chooses_a_substitute(clock):
    raw = {
        "parts": [
            part(
                "p1",
                stack={"business": "가나에너지", "code": "1"},
                pollutants=["nox"],
                time={"kind": "yesterday"},
                metric="derived",
                note="이상치 제외",
            )
        ]
    }
    svc = service(clock, raw)
    first = ask(svc, "가나에너지 굴뚝 1 어제 NOx 튀는 값 제외하고 비교")
    assert first.card.kind == "OPERATION" and "아직 하지 않습니다" in first.card.message
    done = pick(svc, first, "max")
    assert done.status == "ANSWERED" and done.parts[0].numbers[0].name == "max"


def test_derived_part_is_caught_from_its_note_even_if_the_planner_did_not_mark_it(clock):
    raw = {
        "parts": [
            part(
                "p1",
                stack={"business": "가나에너지", "code": "1"},
                pollutants=["nox"],
                time={"kind": "yesterday"},
                note="이상치 제외",
            )
        ]
    }
    first = ask(service(clock, raw), "가나에너지 굴뚝 1 어제 NOx 튀는 값 제외하고 비교")
    assert first.card.kind == "OPERATION" and "아직 하지 않습니다" in first.card.message


def test_a_supported_calculation_does_not_ask_for_an_operation(clock):
    raw = {
        "parts": [
            part(
                "p1",
                stack={"business": "가나에너지", "code": "1"},
                pollutants=["nox"],
                time={"kind": "yesterday"},
                metric="derived",
                note="NOx 어제 최고 시각",
            )
        ]
    }
    response = ask(service(clock, raw), "가나에너지 굴뚝 1 어제 NOx 최고 시각 언제야 그리고 비교")
    assert response.card is None and response.parts[0].label == "극값 시각"
