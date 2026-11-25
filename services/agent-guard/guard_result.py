"""가드레일 검사 호출·응답 해석 규칙 (spec 017, contracts/agent-guard-connection.md).

시험 도구(guard_eval.py)와 에이전트(D, #66)가 같은 규칙을 쓴다. 표준 라이브러리만 쓰고
boto3 클라이언트는 받기만 한다 — 에이전트에 그대로 복사해도 된다.

- 가드레일 정책은 차단·가림으로 만들어 두고, 실제로 막을지는 호출하는 쪽의 적용 목록
  (SSM `/tms/app/config/guardrail-enforce`)으로 정한다. provider가 거부 주제·근거 확인의
  "감지만" 동작을 지원하지 않기 때문이다(research R3).
- 개인정보 가림은 적용 목록과 상관없이 항상 한다. 가드레일이 찾은 일치 문자열을 D와 같은
  표시(`[이메일]` 등)로 바꾼다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

REGION = "ap-northeast-2"
PARAM_PREFIX = "/tms/app/config/guardrail-"
KINDS = ("content", "prompt_attack", "topics", "grounding")

BLOCKED_INPUT = (
    "이 요청은 처리할 수 없습니다. 굴뚝 측정값·대기 법령과 관련된 질문만 도와드릴 수 있습니다."
)
BLOCKED_OUTPUT = "답변을 안전하게 만들 수 없어 표시하지 않습니다. 질문을 바꿔 다시 물어봐 주세요."

# 가드레일 개인정보 종류·정규식 이름 → D(check_input)와 같은 표시
PII_LABELS = {
    "EMAIL": "[이메일]",
    "PHONE": "[전화번호]",
    "kr_phone": "[전화번호]",
    "rrn": "[주민번호]",
    "CREDIT_DEBIT_CARD_NUMBER": "[카드번호]",
}


@dataclass(frozen=True)
class Config:
    id: str
    version: str
    enforce: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Hit:
    """걸린 정책 하나. kind: content·prompt_attack·topics·grounding·pii"""

    kind: str
    name: str
    action: str  # BLOCKED · ANONYMIZED · NONE(감지만)
    detail: str = ""


@dataclass
class Result:
    intervened: bool
    hits: list[Hit] = field(default_factory=list)
    masked_only: bool = False
    text_out: str = ""
    blocked: bool = False
    latency_ms: float = 0.0
    units: dict[str, int] = field(default_factory=dict)

    @property
    def reasons(self) -> list[str]:
        """기록용 사유(개인정보 제외, 중복 없이 순서 유지)."""
        return list(dict.fromkeys(h.name for h in self.hits if h.kind != "pii"))


def parse_enforce(value: str | None) -> frozenset[str]:
    """`content,topics` → {"content", "topics"}. 빈 값·`none` → 빈 집합. 모르는 값은 오류."""
    if not value or value.strip().lower() == "none":
        return frozenset()
    items = {v.strip() for v in value.split(",") if v.strip()}
    unknown = items - set(KINDS)
    if unknown:
        raise ValueError(f"모르는 적용 값: {sorted(unknown)} (허용: {', '.join(KINDS)})")
    return frozenset(items)


def load_config(ssm) -> Config:
    names = [f"{PARAM_PREFIX}{k}" for k in ("id", "version", "enforce")]
    resp = ssm.get_parameters(Names=names)
    got = {p["Name"].removeprefix(PARAM_PREFIX): p["Value"] for p in resp.get("Parameters", [])}
    if "id" not in got or "version" not in got:
        raise KeyError(f"SSM 파라미터 없음: {', '.join(n for n in names[:2])}")
    return Config(got["id"], got["version"], parse_enforce(got.get("enforce")))


def build_content(text: str, grounding: str | None = None, query: str | None = None) -> list:
    """검사 대상 + (근거 확인용) 근거·질문. 근거가 없으면 대상만 보낸다."""
    if not grounding:
        return [{"text": {"text": text}}]
    content = [{"text": {"text": grounding, "qualifiers": ["grounding_source"]}}]
    if query:
        content.append({"text": {"text": query, "qualifiers": ["query"]}})
    content.append({"text": {"text": text, "qualifiers": ["guard_content"]}})
    return content


def check(br, cfg: Config, source: str, text: str, grounding: str | None = None,
          query: str | None = None) -> Result:
    """ApplyGuardrail 한 번. source: INPUT | OUTPUT"""
    started = time.perf_counter()
    resp = br.apply_guardrail(
        guardrailIdentifier=cfg.id,
        guardrailVersion=cfg.version,
        source=source,
        content=build_content(text, grounding, query),
    )
    res = parse(resp, text, cfg.enforce, source)
    if not res.latency_ms:
        res.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return res


def _hit(action: str | None, detected: bool | None) -> bool:
    """정책이 걸렸는가: 동작이 있거나(BLOCKED·ANONYMIZED) 감지 표시가 있음."""
    return (action not in (None, "", "NONE")) or bool(detected)


def _hits(assessment: dict) -> list[Hit]:
    out: list[Hit] = []
    for t in assessment.get("topicPolicy", {}).get("topics", []):
        if _hit(t.get("action"), t.get("detected")):
            out.append(Hit("topics", t.get("name", "?"), t.get("action", "NONE")))
    for f in assessment.get("contentPolicy", {}).get("filters", []):
        if _hit(f.get("action"), f.get("detected")):
            kind = "prompt_attack" if f.get("type") == "PROMPT_ATTACK" else "content"
            out.append(Hit(kind, f.get("type", "?"), f.get("action", "NONE"),
                           str(f.get("confidence", ""))))
    for f in assessment.get("contextualGroundingPolicy", {}).get("filters", []):
        if _hit(f.get("action"), f.get("detected")):
            out.append(Hit("grounding", f.get("type", "?"), f.get("action", "NONE"),
                           f"{f.get('score', '')}/{f.get('threshold', '')}"))
    sens = assessment.get("sensitiveInformationPolicy", {})
    for e in sens.get("piiEntities", []):
        if _hit(e.get("action"), e.get("detected")):
            out.append(Hit("pii", e.get("type", "?"), e.get("action", "NONE"), e.get("match", "")))
    for r in sens.get("regexes", []):
        if _hit(r.get("action"), r.get("detected")):
            out.append(Hit("pii", r.get("name", "?"), r.get("action", "NONE"), r.get("match", "")))
    return out


def mask(text: str, hits: list[Hit]) -> str:
    """가드레일이 찾은 개인정보 일치 문자열을 표시로 바꾼다(긴 것부터)."""
    pii = sorted((h for h in hits if h.kind == "pii" and h.detail), key=lambda h: -len(h.detail))
    for h in pii:
        text = text.replace(h.detail, PII_LABELS.get(h.name, f"[{h.name}]"))
    return text


def parse(resp: dict, original: str, enforce: frozenset[str] | set[str] = frozenset(),
          source: str = "INPUT") -> Result:
    hits: list[Hit] = []
    latency = 0.0
    for a in resp.get("assessments", []):
        hits.extend(_hits(a))
        latency += float(a.get("invocationMetrics", {}).get("guardrailProcessingLatency", 0) or 0)
    blocked = any(h.kind in enforce and h.action == "BLOCKED" for h in hits if h.kind != "pii")
    masked_only = bool(hits) and all(h.kind == "pii" for h in hits)
    if blocked:
        outputs = "".join(o.get("text", "") for o in resp.get("outputs", []))
        text_out = outputs or (BLOCKED_INPUT if source == "INPUT" else BLOCKED_OUTPUT)
    else:
        text_out = mask(original, hits)
    units = {k: int(v) for k, v in resp.get("usage", {}).items() if isinstance(v, int | float)}
    return Result(
        intervened=resp.get("action") == "GUARDRAIL_INTERVENED",
        hits=hits,
        masked_only=masked_only,
        text_out=text_out,
        blocked=blocked,
        latency_ms=round(latency, 1),
        units=units,
    )
