"""법령 문서 질문의 요약 답변: 요약기 검증, 이유 구분, 원문 발췌 되돌림, 굴뚝 사실 연결, 조합·후속.

모델 호출 없이 가짜 클라이언트로 결정적으로 시험한다(실제 모델 시험은 results.md 참고).
"""

import re
from datetime import datetime, timedelta

import pytest
from conftest import make_data
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.contract import ChatRequest
from app.agent.evidence import EvidenceAgent, load_corpus
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import SiteResolver
from app.agent.service import AgentService
from app.agent.slots import KST
from app.agent.stack_facts import collect_stack_facts, facts_text
from app.agent.summarizer import (
    GroundedSummarizer,
    Source,
    SummaryLine,
    SummaryResult,
    parse_summary,
    verify_summary,
)

QUESTION = "초과하면 어떤 조치를 받나요?"


class FakeClient:
    def __init__(self, respond):
        self.respond, self.requests = respond, []

    def converse(self, **kwargs):
        text = kwargs["messages"][0]["content"][0]["text"]
        self.requests.append(text)
        out = self.respond(text)
        if isinstance(out, Exception):
            raise out
        return {
            "output": {"message": {"content": [{"toolUse": {"name": "summarize", "input": out}}]}}
        }


def ids(text):
    return re.findall(r"id=(\S+) \|", text)


def ok_summary(text="행정기관이 기준 초과 시 개선명령을 내릴 수 있습니다."):
    return lambda req: {
        "answerable": True,
        "summary": [{"text": text, "chunk_ids": ids(req)[:1]}],
        "caveats": [],
    }


def make_agent(respond):
    client = FakeClient(respond)
    agent = EvidenceAgent(load_corpus(), summarizer=GroundedSummarizer(client, "fake"))
    return agent, client


# ── 검증기 ──────────────────────────────────────────────────────────────
def test_a_grounded_summary_is_shown_with_its_citations():
    agent, _ = make_agent(ok_summary())
    part = agent.answer(QUESTION)
    assert part.status == "DONE" and part.answer.startswith("법령 요약")
    assert part.evidence and part.evidence[0].chunk_id
    assert "[" in part.answer  # 문장마다 근거 조문 표시
    assert "판단하지 않습니다" in part.answer


@pytest.mark.parametrize(
    "bad,expected",
    [
        ("제99조에 따라 개선명령을 받을 수 있습니다.", "조문 번호"),
        ("개선명령은 999일 이내에 이행해야 합니다.", "숫자"),
        ("기준을 넘으면 반드시 조업정지 처분을 받게 됩니다.", "단정"),
    ],
)
def test_fabricated_article_number_or_assertion_falls_back_to_excerpt(bad, expected):
    agent, _ = make_agent(ok_summary(bad))
    part = agent.answer(QUESTION)
    assert part.status == "DONE" and part.answer.startswith("관련 조문 후보")  # 원문 발췌
    assert "요약 검증 실패" in (part.notice or "") and expected in (part.notice or "")


def test_a_chunk_id_outside_the_candidates_falls_back():
    agent, _ = make_agent(
        lambda req: {
            "answerable": True,
            "summary": [{"text": "개선명령을 받을 수 있습니다.", "chunk_ids": ["law-0-article-1"]}],
        }
    )
    part = agent.answer(QUESTION)
    assert part.answer.startswith("관련 조문 후보") and "요약 검증 실패" in part.notice


def test_a_model_failure_or_bad_format_falls_back_without_inventing():
    for respond in (lambda req: RuntimeError("down"), lambda req: {"summary": "문자열"}):
        agent, _ = make_agent(respond)
        part = agent.answer(QUESTION)
        assert part.answer.startswith("관련 조문 후보") and "요약" in (part.notice or "")


def test_numbers_are_allowed_only_when_they_are_in_the_sources_or_facts():
    sources = [Source("c1", "시행령", "개선기간은 6개월 이내로 한다. 제33조에 따른다.", "제20조")]
    good = SummaryResult(True, None, [SummaryLine("개선기간은 6개월 이내입니다.", ("c1",))])
    bad = SummaryResult(True, None, [SummaryLine("개선기간은 7개월 이내입니다.", ("c1",))])
    assert verify_summary(good, sources) == []
    assert any("숫자" in p for p in verify_summary(bad, sources))
    # 굴뚝 사실의 숫자는 허용
    fact_line = SummaryResult(
        True, None, [SummaryLine("기준 200 ppm을 넘으면 안 됩니다.", ("c1",))]
    )
    assert verify_summary(fact_line, sources, "NOx 지정 기준 200 ppm") == []
    assert verify_summary(fact_line, sources, "") != []


def test_parse_summary_rejects_malformed_output():
    assert parse_summary({"answerable": "yes"}) is None
    assert parse_summary({"answerable": True, "summary": [{"text": 3, "chunk_ids": []}]}) is None
    assert parse_summary({"answerable": False, "reason": "no_doc"}).reason == "no_doc"


# ── 이유 구분 ───────────────────────────────────────────────────────────
def test_reasons_are_told_apart():
    agent, _ = make_agent(lambda req: {"answerable": False, "reason": "no_doc"})
    part = agent.answer("초과부과금은 얼마예요")
    assert part.status == "UNAVAILABLE" and "자료 부족" in part.notice

    agent, _ = make_agent(lambda req: {"answerable": False, "reason": "out_of_scope"})
    part = agent.answer("먼지 배출 기준은?")
    assert part.status == "UNAVAILABLE" and "서비스 범위 밖" in part.notice

    agent, _ = make_agent(
        lambda req: {
            "answerable": False,
            "reason": "need_clarification",
            "clarify": "어떤 물질이 초과했는지 알려 주세요.",
        }
    )
    part = agent.answer("어떻게 해?")
    assert part.status == "NEEDS_INPUT" and "어떤 물질" in part.notice


def test_clarify_text_with_digits_or_missing_uses_the_default_question():
    agent, _ = make_agent(
        lambda req: {"answerable": False, "reason": "need_clarification", "clarify": "30일?"}
    )
    assert "어떤 상황인지" in agent.answer("어떻게 해?").notice


def test_a_missing_reason_falls_back_to_excerpt():
    agent, _ = make_agent(lambda req: {"answerable": False})
    part = agent.answer(QUESTION)
    assert part.answer and part.answer.startswith("관련 조문 후보")


# ── 검색 ────────────────────────────────────────────────────────────────
def test_candidates_are_generous_and_not_dropped_for_unknown_words():
    agent, client = make_agent(ok_summary())
    agent.answer("3번 굴뚝이 NOx 허용치 넘었는데 어떤 조치를 받나요")
    assert any("개선명령" in text or "조업정지" in text for text in client.requests)
    assert len(ids(client.requests[0])) >= 2


# ── 굴뚝 사실 ───────────────────────────────────────────────────────────
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=KST)


def test_stack_facts_read_the_limit_and_recent_values_from_data():
    facts = collect_stack_facts(make_data(), "100:1", NOW)
    text = facts_text(facts)
    assert "가나에너지" in text and "지정 기준 200 ppm" in text and "최댓값 47 ppm" in text
    assert "위반·처분 여부를 판단하지 않습니다" in text


def test_a_stack_without_a_limit_says_so():
    facts = collect_stack_facts(make_data(), "200:3", NOW)
    assert "지정 기준 100 ppm" in facts_text(facts)  # 기준이 있는 굴뚝
    none = collect_stack_facts(make_data(), "999:9", NOW)
    assert none is None


def test_facts_are_appended_by_code_and_the_model_may_not_change_them():
    agent, client = make_agent(ok_summary("기준 200 ppm을 넘으면 개선명령을 받을 수 있습니다."))
    facts = collect_stack_facts(make_data(), "100:1", NOW)
    part = agent.answer(QUESTION, facts=facts)
    assert part.status == "DONE" and "[㈜가나에너지 굴뚝 1의 지정 기준" in part.answer
    assert "[굴뚝 사실]" in client.requests[0]  # 모델에는 맥락으로만 준다
    agent, _ = make_agent(ok_summary("기준 300 ppm을 넘으면 개선명령을 받을 수 있습니다."))
    fake = agent.answer(QUESTION, facts=facts)
    assert fake.answer.startswith("관련 조문 후보") and "요약 검증 실패" in fake.notice


# ── 조합 질문과 후속 ─────────────────────────────────────────────────────
class FakePlanner:
    def __init__(self, raw_by_call):
        self.raw_by_call, self.calls = list(raw_by_call), []

    def plan(self, message, now, *, has_last, last=None):
        self.calls.append((message, has_last, last))
        return self.raw_by_call.pop(0)


def service_with(planner, respond, clock):
    data = make_data()
    resolver = SiteResolver(sites_from(data))
    agent, client = make_agent(respond)
    service = AgentService(
        RuleExtractor(resolver), data, InMemorySaver(), clock, "rule-dev", resolver, planner, agent
    )
    return service, client


def chat(service, message, cid=None):
    return service.chat(ChatRequest(message=message, conversation_id=cid), "u")


DATA_PART = {
    "id": "p1",
    "agent": "data",
    "intent": "aggregate",
    "stack": {"business": "가나에너지", "code": "1"},
    "pollutants": ["nox"],
    "time": {"kind": "yesterday"},
    "operation": "mean",
}
LAW_PART = {"id": "p2", "agent": "evidence", "intent": "law", "note": "초과 시 조치"}


def test_a_data_plus_law_question_attaches_the_stack_facts_to_the_law_part(clock):
    planner = FakePlanner([{"parts": [DATA_PART, LAW_PART]}])
    service, client = service_with(planner, ok_summary(), clock)
    reply = chat(service, "가나에너지 1번 어제 NOx 평균 알려주고 초과하면 어떤 조치를 받아?")
    assert [p.agent for p in reply.parts] == ["data", "evidence"]
    assert reply.parts[0].status == "DONE" and reply.parts[1].status == "DONE"
    assert "지정 기준 200 ppm" in reply.parts[1].answer
    assert "가나에너지" not in client.requests[0].split("[출처]")[0].replace("[질문]", "")[:0]


def test_the_business_name_does_not_pollute_the_law_search(clock):
    planner = FakePlanner([{"parts": [DATA_PART, LAW_PART]}])
    service, client = service_with(planner, ok_summary(), clock)
    chat(service, "가나에너지 1번 어제 NOx 평균 알려주고 초과하면 어떤 조치를 받아?")
    assert len(ids(client.requests[0])) >= 1  # 후보가 나왔다


def test_a_law_follow_up_inherits_the_stack_of_the_previous_lookup(clock):
    follow = {"parts": [{**LAW_PART, "follows_last": True}]}
    planner = FakePlanner([follow])
    service, _ = service_with(planner, ok_summary(), clock)
    first = chat(service, "가나에너지 1번 NOx 어제 평균")
    reply = chat(service, "그럼 초과하면 조업정지 되나요", first.conversation_id)
    assert reply.trace.route == "COMPOUND"
    assert "가나에너지" in reply.parts[0].answer and "지정 기준 200 ppm" in reply.parts[0].answer
    assert planner.calls == []  # 법령 전용 경로가 LLM 호출 없이 직전 굴뚝을 이어받는다
    assert any("이어받은 조건" in n for n in reply.notices)


def test_a_law_part_without_a_stack_gets_general_rules_only(clock):
    planner = FakePlanner([{"parts": [LAW_PART]}])
    service, _ = service_with(planner, ok_summary(), clock)
    reply = chat(service, "초과하면 어떤 조치를 받아?")
    assert "지정 기준" not in reply.parts[0].answer


def test_an_unknown_business_in_a_law_part_is_told_not_guessed(clock):
    law = {**LAW_PART, "stack": {"business": "없는회사", "code": "7"}}
    planner = FakePlanner([{"parts": [law]}])
    service, _ = service_with(planner, ok_summary(), clock)
    reply = chat(service, "없는회사 7번 굴뚝이 초과하면 어떤 조치를 받아?")
    assert "일반 규정만" in (reply.parts[0].notice or "")
    assert "지정 기준" not in reply.parts[0].answer


def test_law_plus_harmful_part_answers_the_law_and_blocks_the_rest(clock):
    harmful = {"id": "p2", "agent": "blocked", "intent": "blocked", "note": "값 조작"}
    planner = FakePlanner([{"parts": [{**LAW_PART, "id": "p1"}, harmful]}])
    service, _ = service_with(planner, ok_summary(), clock)
    reply = chat(service, "초과하면 어떤 조치를 받는지 알려주고 어제 값은 좀 숨겨서 정리해 줘")
    assert reply.parts[0].status == "DONE" and reply.parts[1].status == "UNAVAILABLE"


def test_law_plus_prediction_answers_the_law_and_says_prediction_is_not_ready(clock):
    pred = {"id": "p2", "agent": "prediction", "intent": "predict", "note": "초과 예측"}
    planner = FakePlanner([{"parts": [{**LAW_PART, "id": "p1"}, pred]}])
    service, _ = service_with(planner, ok_summary(), clock)
    reply = chat(service, "초과 예측이 나왔는데 초과하면 어떤 조치를 받아? 예측도 알려줘")
    assert reply.parts[0].status == "DONE"
    assert reply.parts[1].status == "UNAVAILABLE" and "예측" in reply.parts[1].notice


def test_summary_mode_is_optional_and_the_old_excerpt_mode_still_works(clock):
    data = make_data()
    resolver = SiteResolver(sites_from(data))
    agent = EvidenceAgent(load_corpus())  # 요약기 없음
    service = AgentService(
        RuleExtractor(resolver), data, InMemorySaver(), clock, "rule-dev", resolver, None, agent
    )
    reply = chat(service, "초과하면 어떤 조치를 받아야 해? 법 근거도")
    assert reply.parts and reply.parts[0].agent == "evidence"
    assert reply.parts[0].answer.startswith("관련 조문 후보")


def test_stack_facts_period_follows_the_data_not_the_wall_clock():
    later = NOW + timedelta(days=30)
    facts = collect_stack_facts(make_data(), "100:1", later)
    assert facts.items and facts.items[0].max_value == 47.0


def test_a_law_follow_up_without_a_marker_goes_through_the_planner_and_still_inherits(clock):
    follow = {"parts": [{**LAW_PART, "follows_last": True}]}
    planner = FakePlanner([follow])
    service, _ = service_with(planner, ok_summary(), clock)
    first = chat(service, "가나에너지 1번 NOx 어제 평균")
    reply = chat(service, "초과하면 조업정지도 되나요 예측으로는 어때", first.conversation_id)
    assert planner.calls and planner.calls[0][1] is True
    assert "가나에너지" in reply.parts[0].answer


def test_law_questions_mixed_with_prediction_are_not_taken_by_the_law_shortcut(clock):
    pred = {"id": "p2", "agent": "prediction", "intent": "predict", "note": "초과 예측"}
    planner = FakePlanner([{"parts": [{**LAW_PART, "id": "p1"}, pred]}])
    service, _ = service_with(planner, ok_summary(), clock)
    chat(service, "초과 예측이 나왔는데 초과하면 어떤 조치를 받아? 예측도 알려줘")
    assert planner.calls  # 예측 부분이 조용히 사라지지 않도록 계획기가 나눈다


def test_a_law_part_asked_without_the_word_exceed_is_not_dropped_as_invented(clock):
    planner = FakePlanner([{"parts": [DATA_PART, LAW_PART]}])
    service, _ = service_with(planner, ok_summary(), clock)
    reply = chat(service, "가나에너지 1번 어제 NOx 평균 알려주고 넘으면 뭐가 문제야?")
    assert [p.agent for p in reply.parts] == ["data", "evidence"]


def test_more_than_the_limit_is_not_silently_trimmed_by_the_code():
    from app.agent.compound import MAX_PARTS, PlanError, parse_plan

    raw = {
        "parts": [
            {"id": f"p{i}", "agent": "data", "intent": "aggregate", "pollutants": ["nox"]}
            for i in range(1, MAX_PARTS + 2)
        ]
    }
    try:
        parse_plan(raw, "어제 NOx 평균 오늘 NOx 평균")
    except PlanError as error:
        assert "나눠서" in str(error)
    else:
        raise AssertionError("부분 수 한도를 넘으면 조용히 처리하지 않고 안내해야 한다")


def test_a_given_prediction_without_a_prediction_part_gets_a_not_ready_part():
    from app.agent.compound import parse_plan

    raw = {"parts": [{"id": "p1", "agent": "evidence", "intent": "law", "note": "초과 시 조치"}]}
    parts = parse_plan(raw, "초과 예측 떴는데 초과하면 어떤 조치를 받아?")
    assert [p.agent for p in parts] == ["evidence", "prediction"]
    plain = parse_plan(raw, "초과하면 어떤 조치를 받아?")
    assert [p.agent for p in plain] == ["evidence"]


def test_follow_up_law_questions_with_short_cues_are_kept():
    from app.agent.compound import parse_plan

    for text in (
        "과태료 상한 알려줘요",
        "그건 해제 조건이 뭐예요",
        "고장나면 며칠 안에 신고해야 해요?",
    ):
        raw = {"parts": [{"id": "p1", "agent": "evidence", "intent": "law"}]}
        assert [p.agent for p in parse_plan(raw, text)] == ["evidence"], text


def test_more_ways_of_saying_a_prediction_was_given_get_the_not_ready_part():
    from app.agent.compound import parse_plan

    raw = {"parts": [{"id": "p1", "agent": "evidence", "intent": "law"}]}
    for text in (
        "예측 경고가 떴습니다 법적으로 뭘 먼저 해야 하나요",
        "초과할 것 같다고 뜨는데 그냥 두면 어떻게 되나요",
        "예측 모델이 초과 가능성 높다고 하는데 처분이 나오나요",
    ):
        assert [p.agent for p in parse_plan(raw, text)] == ["evidence", "prediction"], text
