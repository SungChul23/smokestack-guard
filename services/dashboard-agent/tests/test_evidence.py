"""근거 에이전트: 조문 단위 검색, 원문 그대로의 발췌, 한계 표시, 지어내지 않음."""

import pytest
from conftest import make_data
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.contract import ChatRequest
from app.agent.evidence import default_agent, load_corpus
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import SiteResolver
from app.agent.router import law_only
from app.agent.service import AgentService


@pytest.fixture(scope="module")
def agent():
    found = default_agent()
    assert found is not None
    return found


@pytest.mark.parametrize(
    ("question", "article"),
    [
        ("측정기기 부착 의무가 뭐야?", "제32조"),
        ("배출허용기준 초과하면 어떤 조치를 받아?", "제34조"),
        ("조업정지는 언제 내려져?", "제34조"),
        ("개선명령 받으면 어떻게 해야해", "제39조"),
    ],
)
def test_the_right_article_is_found(agent, question, article):
    hits = agent.retriever.search(question)
    assert hits and article in [h.chunk.article for h in hits[:3]]


def test_unrelated_questions_get_no_evidence_instead_of_a_guess(agent):
    part = agent.answer("오늘 날씨 어때")
    assert part.status == "UNAVAILABLE" and "지어내지 않습니다" in (part.notice or "")
    assert part.evidence == []


def test_every_excerpt_is_a_verbatim_piece_of_the_source_text(agent):
    corpus = load_corpus()
    texts = {c.id: c.text for c in corpus.chunks}
    for question in ["측정기기 부착 의무", "조업정지 명령", "공란 결측 이유", "개선명령 이행 보고"]:
        for hit in agent.retriever.search(question):
            excerpt = hit.excerpt.rstrip("…")
            assert excerpt in texts[hit.chunk.id], (question, excerpt)


def test_the_answer_cites_the_source_and_never_judges_a_violation(agent):
    part = agent.answer("측정기기 부착 의무가 뭐야?")
    assert part.status == "DONE" and part.evidence[0].url and part.evidence[0].chunk_id
    text = part.answer or ""
    assert "출처:" in text and "판단하지 않습니다" in text
    assert "위반입니다" not in text
    assert part.notice  # 자료의 한계(미확보 별표 등)를 함께 붙인다


def test_only_a_few_chunks_are_read_not_the_whole_document(agent):
    assert len(agent.retriever.search("배출허용기준")) <= 3
    assert len(agent.corpus.chunks) > 10


def test_law_only_detects_questions_without_a_measurement_lookup():
    assert law_only("측정기기 부착 의무가 뭐야?")
    assert not law_only("어제 NOx 평균 알려주고 법 기준도 알려줘")
    assert not law_only("오늘 날씨 어때")


@pytest.fixture
def service(clock):
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


def test_a_law_question_is_answered_by_the_evidence_agent(service):
    response = service.chat(ChatRequest(message="조업정지 명령은 언제 내려져?"), "u")
    assert response.status == "ANSWERED" and response.parts[0].agent == "evidence"
    assert response.parts[0].evidence and response.trace.route == "COMPOUND"


def test_a_data_plus_law_plan_returns_both_parts(clock):
    from app.agent.compound import parse_plan, run_plan

    data = make_data()
    raw = {
        "parts": [
            {
                "id": "p1",
                "agent": "data",
                "intent": "aggregate",
                "stack": {"business": "가나에너지", "code": "1"},
                "pollutants": ["nox"],
                "time": {"kind": "yesterday"},
                "operation": "max",
            },
            {"id": "p2", "agent": "evidence", "intent": "law", "note": "법 기준"},
        ]
    }
    message = "가나에너지 1번 어제 NOx 최댓값 알려주고 법 기준 설명해줘"
    out = run_plan(
        parse_plan(raw, message),
        data,
        SiteResolver(sites_from(data)),
        clock(),
        message,
        default_agent(),
    )
    assert [p.status for p in out] == ["DONE", "DONE"]
    assert out[1].agent == "evidence" and out[1].evidence


def test_a_word_the_documents_do_not_contain_is_named_in_the_answer(agent):
    part = agent.answer("대기오염 방지시설 설치비 지원 법이 있어?")
    assert part.status == "DONE" and part.answer.startswith("질문의 '설치비'에 해당하는 말은")


def test_when_the_key_term_is_missing_from_the_documents_nothing_is_forced(agent):
    part = agent.answer("과징금은 얼마나 부과돼?")  # 과징금 조문은 보관 자료에 없다
    assert part.status == "UNAVAILABLE" and part.evidence == []


def test_law_only_ignores_the_word_stack_but_not_a_measurement_lookup():
    assert law_only("굴뚝 데이터에 공란이 많은 이유가 뭐야")
    assert not law_only("굴뚝 15번 어제 NOx 평균과 법 기준")


# ── 원문 발췌의 "문서에 없는 말" 판정에서 서술어·의문어를 뺀다 (E2E 시험 결함 3) ──────────
# 요약이 실패하거나 거부되었을 때의 안전망이다. 검색은 후보를 찾았는데
# "넘으면·끄면·이행하면·누구·며칠"을
# 핵심어로 세어 절반 넘게 "문서에 없다"로 보고 후보를 버렸다.
@pytest.mark.parametrize(
    ("question", "article"),
    [
        ("굴뚝이 허용기준을 넘으면 어떤 조치를 받나요?", "제33조"),
        ("측정기기를 일부러 끄면 안 되나요?", "제32조"),
        ("개선명령을 이행하면 누구에게 보고해야 하나요?", "제22조"),
        ("개선계획서는 며칠 안에 내야 하나요?", "제21조"),
        ("굴뚝이 허용기준을 넘으면 어떤 조치를 받는지 알려 주세요", "제33조"),  # "받는지·주세요"
        ("허용기준 초과 시 조업정지가 되는지 알려 주세요", "조업정지"),  # "되는지"
    ],
)
def test_extractive_fallback_finds_articles_despite_verbs_and_question_words(question, article):
    from app.agent.evidence import default_agent

    part = default_agent(None).answer(question)
    assert part.status == "DONE"
    assert article in part.answer


@pytest.mark.parametrize(
    "question",
    [
        "초과부과금은 어떻게 계산하나요?",  # 보관한 문서에 없는 주제
        "허가 취소 요건이 뭐예요?",
        "미국 EPA 배출 기준은 어떻게 돼요?",  # 서비스 범위 밖
        "오늘 날씨 어때?",
    ],
)
def test_extractive_fallback_still_refuses_topics_missing_from_the_documents(question):
    from app.agent.evidence import default_agent

    part = default_agent(None).answer(question)
    assert part.status == "UNAVAILABLE"
    assert "지어내지 않습니다" in (part.notice or "")
