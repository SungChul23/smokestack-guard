"""로그 라우터 Lambda (specs/a-platform/014-log-opensearch, research R3·R9).

Firehose는 CloudWatch Logs 묶음을 OpenSearch에 직접 넣지 못한다(여러 줄이 레코드 하나).
그래서 이 함수가 묶음을 풀어 **로그 한 줄 = 레코드 하나**로 만들고, 꼬리표를 붙여 Firehose 3개로 나눈다.

입력
- CloudWatch Logs 구독: {"awslogs": {"data": <base64 gzip>}}
- EventBridge Step Functions 실행 상태 변경: {"source": "aws.states", "detail": {...}}

보낼 곳 (환경 변수로 Firehose 이름)
- 서버 로그 그룹(/tms/app/…)에서 log_type == "activity" → STREAM_ACTIVITY
- 서버 로그 그룹의 나머지 → STREAM_APP
- 그 밖(Lambda·Glue·Step Functions) → STREAM_PIPELINE

로그 본문은 그대로 옮길 뿐 이 함수가 따로 로그에 찍지 않는다(요약만).
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import re
import time
from datetime import UTC, datetime

STREAM_APP = os.environ.get("STREAM_APP", "tms-logs-app")
STREAM_PIPELINE = os.environ.get("STREAM_PIPELINE", "tms-logs-pipeline")
STREAM_ACTIVITY = os.environ.get("STREAM_ACTIVITY", "tms-logs-activity")
APP_PREFIX = "/tms/app/"
BATCH = 500  # PutRecordBatch 한도
MAX_TRIES = 3

_LEVEL_WORDS = ("CRITICAL", "ERROR", "WARNING", "WARN", "INFO", "DEBUG")
_LEVEL_RE = re.compile(r"\[(CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG)\]|^(CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG)[: ]")
_ERROR_HINTS = ("Traceback (most recent call last)", "Task timed out", "Runtime.ExitError", "Exception:")
_FAILED_SFN = {"FAILED", "TIMED_OUT", "ABORTED"}


# ---------------------------------------------------------------------------
# 꼬리표
# ---------------------------------------------------------------------------


def service_name(log_group: str) -> str:
    """/tms/app/api → api, /aws/lambda/tms-collector → tms-collector, /aws-glue/tms-silver → glue-tms-silver."""
    if log_group.startswith(APP_PREFIX):
        return log_group[len(APP_PREFIX):]
    if log_group.startswith("/aws/lambda/"):
        return log_group[len("/aws/lambda/"):]
    if log_group.startswith("/aws-glue/"):
        return "glue-" + log_group[len("/aws-glue/"):].split("/")[0]
    return log_group.strip("/").replace("/", "-")


def _norm_level(word: str) -> str:
    w = word.upper()
    return "WARNING" if w == "WARN" else w


def guess_level(message: str, parsed: dict | None) -> str:
    if parsed:
        lv = parsed.get("level") or parsed.get("levelname")
        if isinstance(lv, str) and lv.upper() in _LEVEL_WORDS:
            return _norm_level(lv)
        status = parsed.get("status")
        if isinstance(status, int):
            if status >= 500:
                return "ERROR"
            if status >= 400:
                return "WARNING"
    if any(h in message for h in _ERROR_HINTS):
        return "ERROR"
    m = _LEVEL_RE.search(message)
    if m:
        return _norm_level(m.group(1) or m.group(2))
    return "INFO"


def _parse_json(message: str) -> dict | None:
    text = message.strip()
    if not text.startswith("{"):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# 입력 → 문서
# ---------------------------------------------------------------------------


def from_cloudwatch(event: dict) -> list[tuple[str, dict]]:
    """CloudWatch 구독 묶음 → [(stream, 문서)]. 제어 메시지는 버린다."""
    payload = json.loads(gzip.decompress(base64.b64decode(event["awslogs"]["data"])))
    if payload.get("messageType") != "DATA_MESSAGE":
        return []
    group = payload.get("logGroup", "")
    stream_name = payload.get("logStream", "")
    service = service_name(group)
    is_app = group.startswith(APP_PREFIX)
    out = []
    for e in payload.get("logEvents", []):
        message = e.get("message", "").rstrip("\n")
        parsed = _parse_json(message)
        doc = {
            "@timestamp": _iso(e["timestamp"]),
            "log_group": group,
            "log_stream": stream_name,
            "service": service,
            "level": guess_level(message, parsed),
            "message": message,
        }
        if parsed is not None:
            doc["json"] = parsed
        if is_app and parsed is not None and parsed.get("log_type") == "activity":
            target = STREAM_ACTIVITY
        elif is_app:
            target = STREAM_APP
        else:
            target = STREAM_PIPELINE
        out.append((target, doc))
    return out


def from_step_functions(event: dict) -> list[tuple[str, dict]]:
    """EventBridge Step Functions 실행 상태 변경 → 파이프라인 문서 1건."""
    d = event.get("detail", {})
    status = d.get("status", "")
    machine = d.get("stateMachineArn", "").rsplit(":", 1)[-1]
    when = d.get("stopDate") or d.get("startDate")
    ts = _iso(int(when)) if isinstance(when, int | float) else event.get("time", _iso(int(time.time() * 1000)))
    doc = {
        "@timestamp": ts,
        "log_group": "eventbridge/step-functions",
        "log_stream": machine,
        "service": machine,
        "level": "ERROR" if status in _FAILED_SFN else "INFO",
        "message": f"Step Functions {machine} {status} {d.get('name', '')}".strip(),
        "json": {
            "log_type": "sfn_execution",
            "status": status,
            "execution": d.get("name"),
            "state_machine": machine,
            "start": _iso(int(d["startDate"])) if isinstance(d.get("startDate"), int | float) else None,
            "stop": _iso(int(d["stopDate"])) if isinstance(d.get("stopDate"), int | float) else None,
        },
    }
    return [(STREAM_PIPELINE, doc)]


def to_docs(event: dict) -> list[tuple[str, dict]]:
    if "awslogs" in event:
        return from_cloudwatch(event)
    if event.get("source") == "aws.states":
        return from_step_functions(event)
    raise ValueError(f"모르는 입력: keys={sorted(event)[:5]}")


# ---------------------------------------------------------------------------
# Firehose로 보내기
# ---------------------------------------------------------------------------


def send(firehose, docs: list[tuple[str, dict]], sleep=time.sleep) -> dict[str, int]:
    """스트림별 PutRecordBatch(500건 단위). 부분 실패는 다시 보내고, 끝내 실패하면 예외(구독이 재시도)."""
    by_stream: dict[str, list[bytes]] = {}
    for stream, doc in docs:
        by_stream.setdefault(stream, []).append((json.dumps(doc, ensure_ascii=False) + "\n").encode("utf-8"))
    counts = {}
    for stream, records in by_stream.items():
        for i in range(0, len(records), BATCH):
            pending = records[i:i + BATCH]
            for attempt in range(MAX_TRIES):
                resp = firehose.put_record_batch(DeliveryStreamName=stream, Records=[{"Data": r} for r in pending])
                if not resp.get("FailedPutCount"):
                    pending = []
                    break
                pending = [r for r, res in zip(pending, resp["RequestResponses"], strict=True) if res.get("ErrorCode")]
                sleep(0.2 * (attempt + 1))
            if pending:
                raise RuntimeError(f"{stream}: {len(pending)}건을 {MAX_TRIES}번 시도해도 보내지 못했다")
        counts[stream] = len(records)
    return counts


_FIREHOSE = None


def handler(event, context=None):
    global _FIREHOSE
    if _FIREHOSE is None:
        import boto3

        _FIREHOSE = boto3.client("firehose", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))
    docs = to_docs(event)
    counts = send(_FIREHOSE, docs) if docs else {}
    print(json.dumps({"records": len(docs), "streams": counts}))
    return {"records": len(docs), "streams": counts}
