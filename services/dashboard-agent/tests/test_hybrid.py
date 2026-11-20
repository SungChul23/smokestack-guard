"""정규식 + LLM 합성 해석기: 확실하면 LLM 없이, 모르면 원문을 보내고, 어긋나면 비운다."""

from datetime import datetime

import pytest
from conftest import make_data

from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.hybrid import HybridExtractor, validate
from app.agent.names import SiteResolver
from app.agent.slots import KST

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=KST)


class FakeLlm:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer or {}, error, []

    def extract(self, message, now, *, has_last):
        self.calls.append(message)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def rule():
    return RuleExtractor(SiteResolver(sites_from(make_data())))


def hybrid(rule, llm):
    return HybridExtractor(rule, llm)


def test_a_complete_rule_result_never_calls_the_llm(rule):
    llm = FakeLlm({"intent": "rank"})
    out = hybrid(rule, llm).extract("가나에너지 굴뚝 1 어제 NOx 평균", NOW, has_last=False)
    assert out["intent"] == "aggregate" and llm.calls == []


def test_missing_stack_sends_the_whole_original_text_to_the_llm(rule):
    llm = FakeLlm({"intent": "aggregate", "time": {"kind": "yesterday"}})
    message = "그 회사 NOx 어제 평균"
    out = hybrid(rule, llm).extract(message, NOW, has_last=False)
    assert llm.calls == [message]  # 정규식 결과가 아니라 원문 그대로
    assert out["intent"] == "aggregate" and out["time"] == {"kind": "yesterday"}


def test_unknown_intent_is_asked_to_the_llm(rule):
    llm = FakeLlm({"intent": "aggregate", "pollutants": ["sox"], "operation": "max"})
    out = hybrid(rule, llm).extract("제일 센 거 알려줘", NOW, has_last=False)
    assert llm.calls and out["intent"] == "aggregate" and out["pollutants"] == ["sox"]


def test_conflicting_time_is_dropped(rule):
    llm = FakeLlm({"intent": "aggregate", "time": {"kind": "today"}})
    out = hybrid(rule, llm).extract("그 회사 NOx 어제 평균", NOW, has_last=False)
    assert llm.calls and out["time"] is None


def test_conflicting_special_intent_is_not_guessed(rule):
    llm = FakeLlm({"intent": "aggregate"})
    out = hybrid(rule, llm).extract("어제 NOx 왜 비어있어", NOW, has_last=False)
    assert llm.calls and out["intent"] == "other"


def test_a_plain_lookup_stays_a_lookup_when_the_llm_says_rank(rule):
    llm = FakeLlm({"intent": "rank"})
    out = hybrid(rule, llm).extract("NOx 최대", NOW, has_last=False)
    assert llm.calls and out["intent"] == "aggregate"  # 빠진 굴뚝은 카드가 묻는다


def test_llm_failure_falls_back_to_the_rule_result(rule):
    llm = FakeLlm(error=RuntimeError("boom"))
    out = hybrid(rule, llm).extract("가나에너지 굴뚝 1 NOx 어제", NOW, has_last=False)
    assert out["intent"] == "aggregate" and out["time"] == {"kind": "yesterday"}


def test_an_invented_business_name_is_dropped(rule):
    llm = FakeLlm({"intent": "aggregate", "stack": {"business": "한화솔루션", "code": "1"}})
    out = hybrid(rule, llm).extract("그 회사 NOx 어제 평균", NOW, has_last=False)
    assert not out["stack"]


def test_a_business_name_present_in_the_text_is_kept(rule):
    llm = FakeLlm({"intent": "aggregate", "stack": {"business": "다라화학", "code": "3"}})
    message = "다라화 NOx 어제 평균 좀 ㅎㅎ 다라화학 3번"
    out = hybrid(rule, llm).extract(message, NOW, has_last=False)
    assert out["stack"]


def test_llm_values_are_validated():
    raw = {
        "intent": "aggregate",
        "pollutants": ["nox", "dust"],
        "time": {"kind": "hours", "value": "100"},
        "operation": "median",
        "metric": "ratio",
    }
    out = validate(raw, "아무 말")
    assert out["pollutants"] == ["nox"]
    assert out["time"] is None and out["operation"] is None and out["metric"] == "ratio"
    assert validate({"time": {"kind": "date", "value": "2026-13-45"}}, "x")["time"] is None
    assert validate({"time": {"kind": "hours", "value": 6}}, "x")["time"] == {
        "kind": "hours",
        "value": 6,
    }


def test_missing_period_or_operation_is_asked_by_a_card_without_calling_the_llm(rule):
    llm = FakeLlm({"intent": "aggregate"})
    out = hybrid(rule, llm).extract("가나에너지 굴뚝 1 NOx", NOW, has_last=False)
    assert llm.calls == [] and out["time"] is None and out["operation"] is None
