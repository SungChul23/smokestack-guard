"""로컬 에이전트 클라이언트: converse()와 같은 모양, 요청 파일을 쓰고 답 파일을 읽는다."""

import json
from datetime import datetime

import pytest

from app.agent.extractor import BedrockExtractor, RuleExtractor
from app.agent.hybrid import HybridExtractor
from app.agent.local_agent import (
    LocalAgentClient,
    LocalAgentPending,
    pending_requests,
    request_key,
)
from app.agent.names import SiteResolver
from app.agent.planner import BedrockPlanner
from app.agent.slots import KST

NOW = datetime(2026, 11, 18, 9, 0, tzinfo=KST)


def test_planner_writes_a_request_then_reads_the_answer(tmp_path):
    planner = BedrockPlanner(LocalAgentClient(tmp_path), "ignored")
    with pytest.raises(LocalAgentPending) as pending:
        planner.plan("가나에너지 1번 어제 NOx 평균이랑 최댓값", NOW, has_last=False)
    files = pending_requests(tmp_path)
    assert [f.stem for f in files] == [pending.value.key]
    request = json.loads(files[0].read_text(encoding="utf-8"))
    assert request["tool"] == "plan" and "계획기" in request["system"]
    assert "2026-11-18" in request["user"] and "parts" in request["schema"]["properties"]
    answer = {"parts": [{"id": "p1", "agent": "data", "intent": "aggregate"}]}
    (tmp_path / "responses" / files[0].name).write_text(json.dumps(answer), encoding="utf-8")
    assert pending_requests(tmp_path) == []
    assert planner.plan("가나에너지 1번 어제 NOx 평균이랑 최댓값", NOW, has_last=False) == answer


def test_the_key_ignores_the_model_name_and_changes_with_the_question(tmp_path):
    a = BedrockPlanner(LocalAgentClient(tmp_path), "m1").request("질문 A", NOW, has_last=False)
    b = BedrockPlanner(LocalAgentClient(tmp_path), "m2").request("질문 A", NOW, has_last=False)
    c = BedrockPlanner(LocalAgentClient(tmp_path), "m1").request("질문 B", NOW, has_last=False)
    assert request_key(a) == request_key(b) != request_key(c)


def test_hybrid_extractor_falls_back_to_the_rule_result_while_the_agent_has_not_answered(
    tmp_path,
):
    rule = RuleExtractor(SiteResolver([]))
    hybrid = HybridExtractor(rule, BedrockExtractor(LocalAgentClient(tmp_path), "x"))
    out = hybrid.extract("제일 센 거 알려줘", NOW, has_last=False)
    assert out["intent"] == "other"  # 답이 없어도 서비스는 안전하게 이어진다
    assert len(pending_requests(tmp_path)) == 1  # 대신 요청은 남는다
