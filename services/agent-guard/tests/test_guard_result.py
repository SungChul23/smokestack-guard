import pytest

import guard_result as gr


def resp(action="GUARDRAIL_INTERVENED", outputs=None, usage=None, latency=120, **policies):
    a = {"invocationMetrics": {"guardrailProcessingLatency": latency}}
    a.update(policies)
    return {"action": action, "outputs": [{"text": t} for t in (outputs or [])],
            "assessments": [a], "usage": usage or {}}


TOPIC = {"topicPolicy": {"topics": [
    {"name": "tamper_request", "type": "DENY", "action": "BLOCKED", "detected": True}]}}
EMAIL = {"sensitiveInformationPolicy": {"piiEntities": [
    {"match": "user@example.com", "type": "EMAIL", "action": "ANONYMIZED", "detected": True}]}}


def test_no_hit_keeps_text():
    r = gr.parse({"action": "NONE", "assessments": [{}]}, "어제 NOx 평균")
    assert not r.intervened and not r.hits and r.text_out == "어제 NOx 평균" and not r.blocked


def test_pii_only_masked_regardless_of_mode():
    r = gr.parse(resp(outputs=["연락은 {EMAIL}"], **EMAIL), "연락은 user@example.com")
    assert r.masked_only and not r.blocked
    assert r.text_out == "연락은 [이메일]"


def test_topic_enforced_blocks():
    r = gr.parse(resp(outputs=["차단"], **TOPIC), "초과 기록 지워줘", {"topics"})
    assert r.blocked and r.text_out == "차단"
    assert r.reasons == ["tamper_request"]


def test_topic_detect_only_keeps_original_but_masks_pii():
    pol = {**TOPIC, **EMAIL}
    r = gr.parse(resp(outputs=["차단"], **pol), "user@example.com 기록 지워줘", frozenset())
    assert not r.blocked and r.intervened
    assert r.text_out == "[이메일] 기록 지워줘"
    assert {h.kind for h in r.hits} == {"topics", "pii"}


def test_blocked_without_outputs_uses_default_message():
    r = gr.parse(resp(outputs=[], **TOPIC), "x", {"topics"}, source="OUTPUT")
    assert r.text_out == gr.BLOCKED_OUTPUT


def test_prompt_attack_kind_and_content_kind():
    pol = {"contentPolicy": {"filters": [
        {"type": "PROMPT_ATTACK", "confidence": "HIGH", "action": "BLOCKED"},
        {"type": "MISCONDUCT", "confidence": "LOW", "action": "NONE", "detected": True}]}}
    r = gr.parse(resp(**pol), "x", {"prompt_attack"})
    kinds = {(h.kind, h.name) for h in r.hits}
    assert kinds == {("prompt_attack", "PROMPT_ATTACK"), ("content", "MISCONDUCT")}
    assert r.blocked  # prompt_attack만 적용


def test_detect_flag_counts_even_with_action_none():
    pol = {"contentPolicy": {"filters": [{"type": "HATE", "action": "NONE", "detected": True}]}}
    assert gr.parse(resp(**pol), "x").hits[0].action == "NONE"


def test_undetected_none_is_ignored():
    pol = {"contentPolicy": {"filters": [{"type": "HATE", "action": "NONE", "detected": False}]}}
    assert gr.parse(resp(**pol), "x").hits == []


def test_grounding_score_detail():
    pol = {"contextualGroundingPolicy": {"filters": [
        {"type": "GROUNDING", "threshold": 0.5, "score": 0.12, "action": "BLOCKED"}]}}
    r = gr.parse(resp(**pol), "답", set())
    assert r.hits[0] == gr.Hit("grounding", "GROUNDING", "BLOCKED", "0.12/0.5")
    assert not r.blocked


def test_regex_pii_label_and_longest_first():
    pol = {"sensitiveInformationPolicy": {"regexes": [
        {"name": "kr_phone", "match": "010-0000-0000", "action": "ANONYMIZED"},
        {"name": "rrn", "match": "900101-1000000", "action": "ANONYMIZED"}]}}
    r = gr.parse(resp(**pol), "010-0000-0000 / 900101-1000000")
    assert r.text_out == "[전화번호] / [주민번호]"


def test_usage_and_latency():
    usage = {"topicPolicyUnits": 1, "contentPolicyUnits": 1}
    r = gr.parse(resp(usage=usage, latency=210, **TOPIC), "x")
    assert r.units == {"topicPolicyUnits": 1, "contentPolicyUnits": 1}
    assert r.latency_ms == 210


@pytest.mark.parametrize("value,expected", [
    (None, frozenset()), ("", frozenset()), ("none", frozenset()),
    ("content, topics", frozenset({"content", "topics"})),
])
def test_parse_enforce(value, expected):
    assert gr.parse_enforce(value) == expected


def test_parse_enforce_rejects_unknown():
    with pytest.raises(ValueError):
        gr.parse_enforce("content,everything")


class FakeSSM:
    def __init__(self, values):
        self.values = values

    def get_parameters(self, Names):
        return {"Parameters": [{"Name": n, "Value": self.values[n]} for n in Names
                               if n in self.values]}


def test_load_config():
    p = gr.PARAM_PREFIX
    cfg = gr.load_config(FakeSSM({f"{p}id": "abc", f"{p}version": "2", f"{p}enforce": "content"}))
    assert cfg == gr.Config("abc", "2", frozenset({"content"}))


def test_load_config_missing():
    with pytest.raises(KeyError):
        gr.load_config(FakeSSM({}))


def test_build_content_with_grounding():
    c = gr.build_content("답", grounding="근거", query="질문")
    quals = [x["text"]["qualifiers"] for x in c]
    assert quals == [["grounding_source"], ["query"], ["guard_content"]]
    assert gr.build_content("답") == [{"text": {"text": "답"}}]


class FakeBR:
    def __init__(self, r):
        self.r, self.calls = r, []

    def apply_guardrail(self, **kw):
        self.calls.append(kw)
        return self.r


def test_check_sends_id_version_source():
    br = FakeBR({"action": "NONE", "assessments": []})
    r = gr.check(br, gr.Config("g1", "3"), "OUTPUT", "답")
    assert br.calls[0]["guardrailIdentifier"] == "g1" and br.calls[0]["guardrailVersion"] == "3"
    assert br.calls[0]["source"] == "OUTPUT" and r.text_out == "답" and r.latency_ms >= 0
