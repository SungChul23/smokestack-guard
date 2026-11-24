"""지식 기반 검색·답변 공통 함수 (spec 016 US3·US4, contracts/ask-cli.md·agent-connection.md).

ask.py·run_eval.py가 쓰고, 에이전트(D)도 같은 규칙을 따른다. 콘솔 시험(2026-11-24)에서 정한 세 가지:
1. 검색은 항상 HYBRID(벡터 + nori 키워드). 기본값은 벡터만이라 "시행령 별표 8"처럼 짧은 문서가
   355조각짜리 시행규칙 별표 8에 묻힌다.
2. 질문이 문서를 지목하면("시행령 별표 8", "관제센터 규정 별표 1") 이름표 필터로 그 문서 안에서 찾는다.
   지목이 둘 이상이면 문서마다 따로 찾아 번갈아 합친다("각각" 질문).
3. 답변 모델에 조각 본문만이 아니라 이름표(법령명·별표·시행일·효력)를 머리말로 붙여 넘긴다.
   본문 중간 조각에는 제목이 없어 모델이 출처를 모르고, 인용도 빠지기 때문이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

REGION = "ap-northeast-2"
SEARCH_TYPE = "HYBRID"
MODELS = {
    "haiku": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "global.anthropic.claude-sonnet-4-6",
}
DEFAULT_MODEL = MODELS["haiku"]

AIR = "대기환경보전법"
TMS_CENTER = "굴뚝 원격감시체계 관제센터의 기능 및 운영 등에 관한 규정"
ENV_TEST = "환경분야 시험ㆍ검사 등에 관한 법률"

# 질문 속 법령 표현 → law_name. 위에서부터 먼저 맞는 것을 쓴다.
_LAW_WORDS: list[tuple[str, str]] = [
    (r"관제센터\s*(?:규정|운영\s*규정)?", TMS_CENTER),
    (r"시험\s*[·ㆍ]?\s*검사\s*(?:등에\s*관한\s*)?법(?:률)?\s*시행규칙", f"{ENV_TEST} 시행규칙"),
    (r"시험\s*[·ㆍ]?\s*검사\s*(?:등에\s*관한\s*)?법(?:률)?\s*시행령", f"{ENV_TEST} 시행령"),
    (r"(?:대기환경보전법\s*)?시행규칙", f"{AIR} 시행규칙"),
    (r"(?:대기환경보전법\s*)?시행령", f"{AIR} 시행령"),
]
_LAW_RE = "|".join(f"(?P<l{i}>{p})" for i, (p, _) in enumerate(_LAW_WORDS))
# 법령 표현(선택) + 0~6글자 사이 + 별표 N(의M) / 제N조
_REF_RE = re.compile(
    rf"(?:(?:{_LAW_RE})[\s\S]{{0,6}}?)?"
    r"(?:\[?\s*별표\s*(?P<appx>\d+)(?:\s*의\s*(?P<sub>\d+))?|제\s*(?P<art>\d+)\s*조)"
)
_PAGE_RE = re.compile(r"쪽 (\d+) -->")


@dataclass(frozen=True)
class Target:
    """질문이 지목한 문서. law_name이 None이면 part만으로 거른다."""

    law_name: str | None
    part: str

    def filter(self) -> dict:
        conds = [{"equals": {"key": "part", "value": self.part}}]
        if self.law_name:
            conds.append({"equals": {"key": "law_name", "value": self.law_name}})
        return _and(conds)

    def label(self) -> str:
        return f"{self.law_name or '(법령 미지정)'} {self.part}"


@dataclass
class Hit:
    rank: int
    score: float
    text: str
    meta: dict
    uri: str
    target: str | None = None  # 어느 지목으로 찾았는지

    @property
    def doc_id(self) -> str:
        return str(self.meta.get("doc_id", "?"))

    @property
    def file(self) -> str:
        return self.uri.split("/", 3)[-1] if self.uri.startswith("s3://") else self.uri

    @property
    def pages(self) -> str:
        p = self.meta.get("x-amz-bedrock-kb-document-page-number")
        if p is not None:
            return str(int(float(p)))
        nums = sorted({int(n) for n in _PAGE_RE.findall(self.text)})
        if not nums:
            return ""
        return str(nums[0]) if len(nums) == 1 else f"{nums[0]}~{nums[-1]}"

    def cite(self) -> str:
        """근거 한 줄: 법령명 + 별표/본문 제목 + 시행일 + 효력"""
        m = self.meta
        title = m.get("title_ko", "")
        law = m.get("law_name", "")
        name = title if title.startswith(law) else f"{law} {title}".strip()
        bits = [f"{m.get('effective_date', '?')} 시행", str(m.get("effective_status", "?"))]
        return f"{name} ({', '.join(bits)})"


@dataclass
class Result:
    question: str
    targets: list[Target]
    hits: list[Hit] = field(default_factory=list)
    fallback: bool = False  # 지목 필터 결과가 비어 필터 없이 다시 찾음


def _and(conds: list[dict]) -> dict:
    return conds[0] if len(conds) == 1 else {"andAll": conds}


def find_targets(question: str) -> list[Target]:
    """질문에서 "시행령 별표 8", "관제센터 규정 별표 1", "시행규칙 제15조" 같은 지목을 찾는다.

    - 별표 N(의M) → part=별표N(의M). 바로 앞(6글자 안)에 법령 표현이 있으면 law_name도 건다.
    - 제N조 → 법령 표현이 있을 때만 그 법령의 본문(part=본문). 법령 없는 "제N조"는 무엇인지 몰라 무시.
    - 법령 표현 없이 "별표 N"만 있으면 앞서 나온 법령을 이어받지 않는다(part만).
    """
    out: list[Target] = []
    for m in _REF_RE.finditer(question):
        law = next((name for i, (_, name) in enumerate(_LAW_WORDS) if m.group(f"l{i}")), None)
        if m.group("appx"):
            part = f"별표{m.group('appx')}" + (f"의{m.group('sub')}" if m.group("sub") else "")
            t = Target(law, part)
        elif law:
            t = Target(law, "본문")
        else:
            continue
        if t not in out:
            out.append(t)
    return out


def status_filter(statuses: list[str] | None) -> dict | None:
    if not statuses:
        return None
    return {"in": {"key": "effective_status", "value": list(statuses)}}


def _one(rt, kb: str, question: str, top: int, flt: dict | None) -> list[dict]:
    vc: dict = {"numberOfResults": top, "overrideSearchType": SEARCH_TYPE}
    if flt:
        vc["filter"] = flt
    resp = rt.retrieve(knowledgeBaseId=kb, retrievalQuery={"text": question},
                       retrievalConfiguration={"vectorSearchConfiguration": vc})
    return resp.get("retrievalResults", [])


def _hit(r: dict, target: str | None) -> Hit:
    loc = r.get("location", {}).get("s3Location", {}).get("uri", "")
    return Hit(0, float(r.get("score", 0.0)), r.get("content", {}).get("text", ""),
               dict(r.get("metadata", {})), loc, target)


def retrieve(rt, kb: str, question: str, top: int = 5, statuses: list[str] | None = None,
             targets: list[Target] | None = None) -> Result:
    """HYBRID 검색 결과를 여러 줄로 모아 번갈아 합친다. 줄 순서(앞일수록 먼저 자리를 얻음):

    1. 지목 문서마다 그 문서 안 검색 (질문이 "시행령 별표 8"처럼 지목했을 때)
    2. 현행 문서만 검색 (--status를 주지 않았을 때). 구판 업무편람(807조각)이 같은 내용을 여러 번 담고 있어
       현행 근거(예: 정도검사 주기 = 형식승인 고시 별표 7)가 상위 밖으로 밀리기 때문(2026-11-24).
    3. 필터 없는 검색(--status를 주면 그 효력만). 지목 문서가 다른 문서를 가리킬 때(관제센터 별표 2 →
       시행규칙 별표 8 제3호 라목 6) 그쪽 조각과 구판 편람 질의·회신도 들어오게.
    """
    targets = find_targets(question) if targets is None else targets
    res = Result(question, targets)
    base = status_filter(statuses)
    rows: list[list[Hit]] = []
    for t in targets:
        flt = _and([t.filter(), base]) if base else t.filter()
        rows.append([_hit(r, t.label()) for r in _one(rt, kb, question, top, flt)])
    res.fallback = bool(targets) and not any(rows)
    if not statuses:
        rows.append([_hit(r, None) for r in _one(rt, kb, question, top, status_filter(["현행"]))])
    rows.append([_hit(r, None) for r in _one(rt, kb, question, top, base)])
    limit = max(top, 2 * len(rows))
    seen: set[str] = set()
    for i in range(max((len(r) for r in rows), default=0)):
        for row in rows:
            if i < len(row) and row[i].text not in seen and len(res.hits) < limit:
                seen.add(row[i].text)
                res.hits.append(row[i])
    for n, h in enumerate(res.hits, start=1):
        h.rank = n
    return res


SYSTEM_PROMPT = """너는 굴뚝 원격감시(TMS)·대기환경 법령 안내 도우미다. 아래 [근거]만으로 한국어로 답한다.

규칙:
- 근거마다 머리말(법령명·별표/본문·시행일·효력)이 있다. 같은 번호의 별표라도 법령(시행령/시행규칙/고시)이 다르면 다른 문서다.
- 답의 각 문장 끝에 근거 번호를 [1]처럼 붙인다. 번호는 [근거]에 붙은 번호를 그대로 쓰고 바꾸지 않는다. 본문에서 법령을 말할 때는 머리말의 법령명·별표·시행일을 쓴다.
- 답 끝에 "출처" 목록을 따로 쓰지 않는다(도구가 근거 목록을 붙인다).
- 효력이 "구판"인 근거(업무편람 2024.12)는 "구판 업무편람에 따르면"이라고 밝히고, 현행 법령 근거와 다르면 현행 법령을 따른다.
- 머리말 주의에 "부과금 숫자 인용 금지"가 있으면 그 근거의 금액·지수 숫자는 쓰지 않는다.
- 근거에 없는 숫자·조문은 만들지 않는다. 질문의 일부를 근거에서 찾지 못하면 그 부분만 "근거 문서에서 찾지 못했다"고 말하고 나머지는 답한다."""


def context_block(hits: list[Hit]) -> str:
    parts = []
    for h in hits:
        head = f"[{h.rank}] {h.cite()}"
        if h.pages:
            head += f" · 쪽 {h.pages}"
        caveat = h.meta.get("caveat")
        if caveat:
            head += f"\n주의: {caveat}"
        parts.append(f"{head}\n{h.text.strip()}")
    return "\n\n".join(parts)


def resolve_model(name: str | None) -> str:
    name = name or DEFAULT_MODEL
    return MODELS.get(name, name)


def answer(br, result: Result, model: str | None = None, max_tokens: int = 3000) -> dict:
    """Converse로 답변. 반환: {"text", "model", "tokens_in", "tokens_out"}"""
    mid = resolve_model(model)
    user = f"[근거]\n{context_block(result.hits)}\n\n[질문]\n{result.question}"
    resp = br.converse(
        modelId=mid,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
    )
    text = "".join(c.get("text", "") for c in resp["output"]["message"]["content"])
    usage = resp.get("usage", {})
    return {"text": text, "model": mid, "tokens_in": usage.get("inputTokens", 0),
            "tokens_out": usage.get("outputTokens", 0)}
