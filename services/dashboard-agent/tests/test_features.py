"""굴뚝 전부 · 최근 N일 · 일일 요약: 단일 질문에서도 끝까지 가는지."""

from conftest import make_data
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.contract import ChatRequest
from app.agent.evidence import default_agent
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import SiteResolver
from app.agent.router import asks_all_stacks, report_only
from app.agent.service import AgentService


def make(clock):
    data = make_data()
    resolver = SiteResolver(sites_from(data))
    return AgentService(
        RuleExtractor(resolver),
        data,
        InMemorySaver(),
        clock,
        "rule-dev",
        resolver,
        None,
        default_agent(),
    )


def ask(service, message):
    return service.chat(ChatRequest(message=message), "u")


def test_site_with_all_its_stacks_is_one_question(clock):
    response = ask(make(clock), "가나에너지 굴뚝 전부 어제 NOx 평균")
    assert response.status == "ANSWERED"
    assert "굴뚝 1:" in response.parts[0].answer and "굴뚝 2:" in response.parts[0].answer


def test_the_last_three_days_become_72_hours_and_four_days_are_asked(clock):
    ok = ask(make(clock), "가나에너지 굴뚝 1 최근 3일 NOx 평균")
    assert ok.status == "ANSWERED" and "72" in ok.parts[0].answer
    asked = ask(make(clock), "가나에너지 굴뚝 1 최근 5일 NOx 평균")
    assert asked.card.kind == "PERIOD"


def test_a_daily_summary_question_is_answered_by_the_report_agent(clock):
    response = ask(make(clock), "어제 전국 일일 요약해줘")
    assert response.status == "ANSWERED" and response.parts[0].agent == "report"
    answer = response.parts[0].answer
    assert "전국 요약" in answer and "NOx:" in answer and "SOx:" in answer
    assert "판정하지 않습니다" in response.parts[0].notice


def test_router_helpers():
    assert report_only("어제 전국 일일 요약해줘") and not report_only("가나에너지 1번 요약")
    assert asks_all_stacks("가나에너지 굴뚝 전부 보여줘") and not asks_all_stacks("가나에너지 1번")


def test_the_period_phrase_is_not_read_as_a_stack_number():
    resolver = SiteResolver(sites_from(make_data()))
    assert resolver.clean_mention("가나에너지 최근 3일 NOx") == "가나에너지"
    assert report_only("어제 전국 요약") and not report_only("가나에너지 1번 요약")


def test_router_flags_time_of_extreme_and_article_requests():
    from app.agent.router import complex_reasons

    assert complex_reasons("남해화학 15번 어제 NOx 제일 높았던 시각 언제야")
    assert complex_reasons("남해화학 15번 어제 NOx 최댓값 알려주고 관련 조문도 알려줘")
