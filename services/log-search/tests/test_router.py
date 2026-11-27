"""라우터 Lambda (014 T009): 묶음 풀기, 꼬리표, 나누기, Step Functions 이벤트, 부분 실패 재전송."""

from __future__ import annotations

import base64
import gzip
import json

import pytest

import router as r


def cw_event(group: str, messages: list[str], kind: str = "DATA_MESSAGE") -> dict:
    payload = {
        "messageType": kind,
        "logGroup": group,
        "logStream": "s1",
        "logEvents": [{"id": str(i), "timestamp": 1763700000000 + i, "message": m} for i, m in enumerate(messages)],
    }
    return {"awslogs": {"data": base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()}}


class FakeFirehose:
    def __init__(self, fail_first: int = 0, always_fail: bool = False):
        self.calls: list[tuple[str, list[bytes]]] = []
        self.fail_first, self.always_fail = fail_first, always_fail

    def put_record_batch(self, DeliveryStreamName, Records):
        self.calls.append((DeliveryStreamName, [x["Data"] for x in Records]))
        n = len(Records)
        if self.always_fail:
            return {"FailedPutCount": n, "RequestResponses": [{"ErrorCode": "ServiceUnavailable"}] * n}
        if self.fail_first:
            k = min(self.fail_first, n)
            self.fail_first = 0
            return {"FailedPutCount": k,
                    "RequestResponses": [{"ErrorCode": "X"}] * k + [{"RecordId": "ok"}] * (n - k)}
        return {"FailedPutCount": 0, "RequestResponses": [{"RecordId": "ok"}] * n}


def test_app_batch_is_split_per_line_and_routed():
    ev = cw_event("/tms/app/api", [
        '{"log_type": "request", "method": "GET", "path": "/api/day", "status": 200, "duration_ms": 350.0}',
        '{"log_type": "activity", "event": "favorite_add", "sub": "u1", "target": "170039"}',
        "ERROR RDS 연결 실패: OperationalError",
    ])
    docs = r.to_docs(ev)
    assert [s for s, _ in docs] == [r.STREAM_APP, r.STREAM_ACTIVITY, r.STREAM_APP]
    req, act, err = (d for _, d in docs)
    assert req["service"] == "api" and req["log_group"] == "/tms/app/api" and req["level"] == "INFO"
    assert req["json"]["duration_ms"] == 350.0 and req["@timestamp"].endswith("Z")
    assert act["json"]["event"] == "favorite_add"
    assert err["level"] == "ERROR" and "json" not in err


@pytest.mark.parametrize("msg,level", [
    ('{"log_type": "request", "status": 503}', "ERROR"),
    ('{"log_type": "request", "status": 403}', "WARNING"),
    ('{"level": "warn", "msg": "x"}', "WARNING"),
    ("[ERROR]\t2026-11-21T00:00:00Z\tabc\tboom", "ERROR"),
    ("Traceback (most recent call last):", "ERROR"),
    ("2026-11-21T00:00:00Z abc Task timed out after 900.00 seconds", "ERROR"),
    ("INFO:     Started server process [1]", "INFO"),
    ("WARNING: something", "WARNING"),
    ("plain text", "INFO"),
])
def test_level_guess(msg, level):
    assert r.to_docs(cw_event("/aws/lambda/tms-collector", [msg]))[0][1]["level"] == level


def test_pipeline_groups_and_service_names():
    for group, svc in [("/aws/lambda/tms-collector", "tms-collector"), ("/aws-glue/tms-silver", "glue-tms-silver"),
                       ("/tms/app/agent", "agent")]:
        stream, doc = r.to_docs(cw_event(group, ["x"]))[0]
        assert doc["service"] == svc
        assert stream == (r.STREAM_APP if group.startswith("/tms/app/") else r.STREAM_PIPELINE)


def test_activity_only_from_app_groups():
    # Lambda 로그에 activity라고 써도 활동으로 보지 않는다
    stream, _ = r.to_docs(cw_event("/aws/lambda/x", ['{"log_type": "activity", "event": "session"}']))[0]
    assert stream == r.STREAM_PIPELINE


def test_control_message_dropped():
    assert r.to_docs(cw_event("/tms/app/api", ["CWL CONTROL MESSAGE"], kind="CONTROL_MESSAGE")) == []


def test_step_functions_event():
    ev = {"source": "aws.states", "detail-type": "Step Functions Execution Status Change", "time": "2026-11-21T18:30:00Z",
          "detail": {"status": "FAILED", "name": "exec-1",
                     "stateMachineArn": "arn:aws:states:ap-northeast-2:1:stateMachine:tms-silver2-ktms",
                     "startDate": 1763749800000, "stopDate": 1763750400000}}
    [(stream, doc)] = r.to_docs(ev)
    assert stream == r.STREAM_PIPELINE and doc["service"] == "tms-silver2-ktms" and doc["level"] == "ERROR"
    assert doc["json"]["status"] == "FAILED" and doc["json"]["execution"] == "exec-1"
    ok = dict(ev, detail=dict(ev["detail"], status="SUCCEEDED"))
    assert r.to_docs(ok)[0][1]["level"] == "INFO"


def test_unknown_input_raises():
    with pytest.raises(ValueError):
        r.to_docs({"foo": 1})


def test_send_groups_by_stream_in_batches_of_500():
    fh = FakeFirehose()
    docs = [(r.STREAM_APP, {"i": i}) for i in range(1200)] + [(r.STREAM_ACTIVITY, {"i": 0})]
    counts = r.send(fh, docs, sleep=lambda _s: None)
    assert counts == {r.STREAM_APP: 1200, r.STREAM_ACTIVITY: 1}
    assert [len(recs) for s, recs in fh.calls if s == r.STREAM_APP] == [500, 500, 200]
    assert all(rec.endswith(b"\n") for _, recs in fh.calls for rec in recs)
    assert json.loads(fh.calls[0][1][0]) == {"i": 0}


def test_send_retries_only_failed_records():
    fh = FakeFirehose(fail_first=2)
    r.send(fh, [(r.STREAM_APP, {"i": i}) for i in range(5)], sleep=lambda _s: None)
    assert [len(recs) for _, recs in fh.calls] == [5, 2]


def test_send_raises_after_retries():
    with pytest.raises(RuntimeError):
        r.send(FakeFirehose(always_fail=True), [(r.STREAM_APP, {"i": 1})], sleep=lambda _s: None)


# --- 017 FR-020: 활동 기록 개인정보 가림 ---

FAKE = "주민 900101-1234567 카드 4111-1111-1111-1111 휴대폰 010-1234-5678로 유선 02-123-4567 메일 user@example.com"


def test_agent_guard_question_and_message_are_masked():
    line = json.dumps({"log_type": "activity", "event": "agent_guard", "layer": "regex",
                       "action": "BLOCKED", "reason": "DATA_TAMPERING", "question": FAKE},
                      ensure_ascii=False)
    stream, doc = r.to_docs(cw_event("/tms/app/agent", [line]))[0]
    assert stream == r.STREAM_ACTIVITY
    for text in (doc["json"]["question"], doc["message"]):
        for raw in ("900101-1234567", "4111-1111-1111-1111", "010-1234-5678", "02-123-4567",
                    "user@example.com"):
            assert raw not in text
    assert doc["json"]["question"] == (
        "주민 [주민번호] 카드 [카드번호] 휴대폰 [전화번호]로 유선 [전화번호] 메일 [이메일]")


def test_masking_keeps_numbers_dates_and_labels():
    q = "2026-11-12 시행, NOx 32.5ppm, 사업장 170902, [전화번호]로 연락 온 건"
    line = json.dumps({"log_type": "activity", "event": "agent_guard", "question": q},
                      ensure_ascii=False)
    _, doc = r.to_docs(cw_event("/tms/app/agent", [line]))[0]
    assert doc["json"]["question"] == q


def test_non_activity_docs_are_not_masked():
    line = '{"log_type": "request", "path": "/api/day", "note": "010-1234-5678"}'
    stream, doc = r.to_docs(cw_event("/tms/app/api", [line]))[0]
    assert stream == r.STREAM_APP and "010-1234-5678" in doc["message"]
