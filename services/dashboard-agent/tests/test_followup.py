"""후속 질문 이어받기: 단일 흐름·계획기 경로(follows_last)·사업장 번호 우선."""

from conftest import make_data
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.compound import PlanPart, fill_from_last, parse_plan
from app.agent.contract import ChatRequest
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import Site, SiteResolver
from app.agent.service import AgentService

USER = "u"


def ask(service, message, cid=None):
    return service.chat(ChatRequest(message=message, conversation_id=cid), USER)


class RecordingPlanner:
    def __init__(self, raw):
        self.raw, self.calls = raw, []

    def plan(self, message, now, *, has_last, last=None):
        self.calls.append((message, has_last, last))
        return self.raw


def planner_service(clock, planner):
    data = make_data()
    resolver = SiteResolver(sites_from(data))
    return AgentService(
        RuleExtractor(resolver), data, InMemorySaver(), clock, "rule-dev", resolver, planner
    )


def test_period_only_followup_inherits_previous_query(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "오늘은?", first.conversation_id)
    assert second.trace.route == "DATA"
    assert "가나에너지" in second.parts[0].answer
    assert "NOx" in second.parts[0].answer


def test_number_only_followup_keeps_site_and_says_so(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "2번은?", first.conversation_id)
    assert second.trace.route == "DATA"
    assert "굴뚝 2" in second.parts[0].answer
    assert any("직전 조회" in n for n in second.notices)


def test_number_with_other_slots_but_no_site_name_inherits_site(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "2번 굴뚝은 어제 NOx 얼마예요", first.conversation_id)
    assert second.parts and "굴뚝 2" in second.parts[0].answer


def test_part_of_day_is_not_read_as_whole_day(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "어제 밤은?", first.conversation_id)
    assert second.card is not None and second.card.kind == "PERIOD"


def test_part_of_day_in_a_new_question_asks_period_card(service):
    reply = ask(service, "가나에너지 1번 NOx 어제 밤 평균")
    assert reply.card is not None and reply.card.kind == "PERIOD"


def test_no_inheritance_without_previous_query(service):
    reply = ask(service, "3번은?")
    assert reply.trace.route == "OUT_OF_SCOPE"


def test_standalone_question_is_not_taken_as_followup(service):
    ask(service, "가나에너지 1번 NOx 어제 평균")
    reply = service.chat(ChatRequest(message="다라화학 3번 NOx 어제 평균"), USER)
    assert "다라화학" in reply.parts[0].answer


# ── 계획기 경로 ───────────────────────────────────────────────────────
def test_planner_receives_previous_query_text(clock):
    raw = {"parts": [{"id": "p1", "agent": "data", "intent": "aggregate", "follows_last": True}]}
    planner = RecordingPlanner(raw)
    service = planner_service(clock, planner)
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    ask(service, "그 전날은요", first.conversation_id)
    message, has_last, last = planner.calls[0]
    assert has_last and "가나에너지" in last and "nox" in last and "yesterday" in last


def test_planner_followup_fills_blanks_only_when_model_says_follow_up(clock):
    raw = {
        "parts": [
            {
                "id": "p1",
                "agent": "data",
                "intent": "aggregate",
                "time": {"kind": "today"},
                "follows_last": True,
            }
        ]
    }
    service = planner_service(clock, RecordingPlanner(raw))
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "어제 말고 오늘로 해줘", first.conversation_id)
    assert second.trace.route == "COMPOUND"
    answer = second.parts[0].answer
    assert "가나에너지" in answer and "NOx" in answer
    assert any("이어받은 조건" in n for n in second.notices)


def test_planner_unrelated_question_does_not_inherit(clock):
    raw = {"parts": [{"id": "p1", "agent": "data", "intent": "aggregate", "follows_last": False}]}
    service = planner_service(clock, RecordingPlanner(raw))
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "그리고 그 값이 왜 그런지도 알려줘", first.conversation_id)
    assert second.parts[0].status == "NEEDS_INPUT"  # 굴뚝을 이어받지 않고 사람에게 묻는다


def test_fill_from_last_keeps_stated_slots_and_unclear():
    data = make_data()
    last = {
        "stack": {"stack_key": "100:1"},
        "pollutants": ["nox"],
        "time": {"kind": "yesterday"},
        "operation": "mean",
    }
    keep = PlanPart(
        id="p1",
        agent="data",
        intent="aggregate",
        pollutants=["sox"],
        time=None,
        follows_last=True,
        unclear=["time"],
    )
    assert fill_from_last([keep], last, data) == ["굴뚝", "집계"]
    assert keep.pollutants == ["sox"] and keep.time is None  # 말한 칸·확신 없는 칸은 그대로
    alone = PlanPart(id="p2", agent="data", intent="aggregate", follows_last=False)
    assert fill_from_last([alone], last, data) == [] and alone.stack is None


def test_follows_last_is_boolean_only():
    parts = parse_plan(
        {"parts": [{"id": "p1", "agent": "data", "intent": "aggregate", "follows_last": "true"}]},
        "그 전날은요",
    )
    assert parts[0].follows_last is False  # 문자열 "true"는 믿지 않는다


# ── 사업장 번호 우선 ───────────────────────────────────────────────────
def test_same_name_sites_narrowed_by_stated_code():
    sites = [
        Site("301", "동서식품(주)", "충청북도", "청주시", ("1",)),
        Site("302", "동서식품(주)", "인천광역시", "서구", ("1", "2")),
    ]
    resolver = SiteResolver(sites)
    assert resolver.resolve("동서식품 1번").outcome == "CARD"  # 둘 다 1번이 있어 사람이 고른다
    found = resolver.resolve("동서식품 2번")
    assert found.outcome == "AUTO" and found.by_code and found.sites[0].site_id == "302"


def test_similar_site_with_code_is_offered_not_chosen():
    resolver = SiteResolver(sites_from(make_data()))
    names = [s.business for s in resolver.similar_with_code("가나에너지", "2")]
    assert names == ["㈜가나에너지"]
    assert resolver.similar_with_code("가나에너지", "9") == []


def test_requery_repeats_previous_conditions(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "다시 조회해줘", first.conversation_id)
    assert second.trace.route == "DATA" and "가나에너지" in second.parts[0].answer


def test_unrelated_words_are_not_taken_as_followup(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "오늘 날씨 어때", first.conversation_id)
    assert second.trace.route == "OUT_OF_SCOPE"  # 모르는 말이 남으면 직전 조회를 붙이지 않는다


def test_number_only_after_ranking_asks_which_stack(service):
    first = ask(service, "NOx 어제 전국 순위 상위 3곳")
    second = ask(service, "2번으로 해줘", first.conversation_id)
    assert second.trace.reason == "NEED_STACK" and not second.parts


def test_hours_ago_is_asked_not_guessed(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "두 시간 전으로 해봐", first.conversation_id)
    assert second.card is not None and second.card.kind == "PERIOD"


def test_unreadable_followup_goes_to_planner_when_previous_query_exists(clock):
    raw = {"parts": [{"id": "p1", "agent": "data", "intent": "aggregate", "follows_last": True}]}
    planner = RecordingPlanner(raw)
    service = planner_service(clock, planner)
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "두 번째 굴뚝은?", first.conversation_id)
    assert planner.calls and second.trace.route == "COMPOUND"
    assert second.parts[0].status in ("DONE", "NEEDS_INPUT")


def test_unrecognized_business_name_is_not_treated_as_number_only(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "마루제지 7번 굴뚝 SOx 오늘 평균", first.conversation_id)
    assert not second.parts  # 직전 사업장(가나에너지)의 7번으로 조용히 답하지 않는다
    assert not any("직전 조회" in n for n in second.notices)


def test_one_more_time_repeats_previous_query(service):
    first = ask(service, "가나에너지 1번 NOx 어제 평균")
    second = ask(service, "한번만 더", first.conversation_id)
    assert second.trace.route == "DATA" and "가나에너지" in second.parts[0].answer
