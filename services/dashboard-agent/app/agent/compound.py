"""복합 질문: 계획(부분 목록)을 검증하고 부분별로 실행한다.

계획은 LLM 분류기(또는 시험용 가짜)가 내고, 이 모듈의 코드가 검증한다. 모델은 조건만 고르고
숫자는 도구가 계산한다. 못 하는 부분은 숨기지 않고 부분마다 상태와 이유를 돌려준다.
설계: specs/d-analytics/314-front-interpretation-decisions/compound-plan.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.agent.contract import Part
from app.agent.evidence import EvidenceAgent
from app.agent.fold import fold
from app.agent.handlers import (
    run_aggregate,
    run_diff,
    run_exceedance,
    run_extreme_time,
    run_freshness,
    run_gap,
    run_rank,
    run_site_stacks,
)
from app.agent.hybrid import clean_time
from app.agent.names import SiteResolver, canon, sido_key
from app.agent.region import explanation, is_group_like, profile_for
from app.agent.report import run_report
from app.agent.slots import (
    DEFAULT_TOP_N,
    MAX_TOP_N,
    REQUIRED,
    UnsupportedPeriod,
    rank_order,
    resolve_period,
)
from app.agent.stack_facts import StackFacts, collect_stack_facts
from app.agent.tools import DataSource

MAX_PARTS = (
    4  # 한 질문에서 처리하는 부분 수. 넘으면 나눠서 묻게 한다(부분이 많을수록 계획 오류가 늘어난다)
)
AGENT_INTENTS: dict[str, set[str]] = {
    "data": {"aggregate", "rank", "freshness", "gap"},
    "evidence": {"law"},
    "prediction": {"predict"},
    "report": {"report"},
    "blocked": {"blocked", "out_of_scope"},
}
UNSUPPORTED_TEXT = {
    "evidence": "법령 근거 검색은 아직 지원하지 않습니다.",
    "prediction": "예측은 아직 지원하지 않습니다.",
    "report": "요약 리포트는 아직 지원하지 않습니다.",
    "blocked": "이 요청은 처리하지 않습니다.",
}
AGENT_LABEL = {
    "data": "현황",
    "evidence": "규정",
    "prediction": "예측",
    "report": "요약",
    "blocked": "차단",
}
_PART_AGENTS = {"data", "evidence", "prediction", "report"}  # Part.agent 값
POLLUTANTS = {"nox", "sox"}
# 모델이 낸 값이 질문 문장에 실제로 근거가 있는지 확인하는 단서(지어낸 값은 버리고 카드로 묻는다)
_POLLUTANT_CUE = {
    "nox": re.compile(r"nox|녹스|엔옥스|엔오엑스|질소산화물"),
    "sox": re.compile(r"sox|속스|삭스|에스옥스|에스오엑스|황산화물"),
}
_OPERATION_CUE = {
    "mean": re.compile(r"평균|mean|avg|average"),
    "max": re.compile(r"최댓?값|최대|최고|맥스|\bmax|높|제일\s*큰|가장\s*큰"),
    "min": re.compile(r"최솟?값|최소|최저|\bmin|낮|적은|작은"),
    "sum": re.compile(r"합계|총합|총량|\bsum|합산"),
}
# 값끼리 계산하는 요청(증감·차이·초과 횟수·가장 높았던 시각)은 계획기가 표시하지 못해도 걸러 낸다
_DERIVED_CUE = re.compile(
    r"넘은\s*횟수|초과\s*(?:횟수|시간)|몇\s*번\s*넘|연속(?:으로)?\s*(?:넘|초과)|증감|차이|"
    r"올랐|내렸|떨어졌|변화율|가장\s*높았던\s*시각|언제\s*(?:제일|가장)\s*높"
    r"|이상치|튀는\s*값|제외하고|빼고\s*계산|반올림|보정|(?:최고|최대|최저|최소)\s*시각|시각이?\s*언제"
)
# 근거·예측·요약·화면 부분은 질문이 그것을 요청하는 말이 있을 때만 인정한다(지어낸 부분은 버린다)
_AGENT_CUE = {
    "evidence": re.compile(
        r"법|규정|기준|의무|조항|조문|근거|허가|과징금|조치|시행규칙|배출허용|규제|처벌|위반|초과"
        r"|넘으면|넘었|넘는|넘어서|문제|어떻게\s*(?:돼|되|해야|하나)|처분|정지|개선|명령|불이익|벌금|책임"
        r"|과태료|신고|보관|기한|해제|이의|며칠|계획서|자가측정|측정기|운영기록|제출|보고|점검|교정|고장"
    ),
    "prediction": re.compile(
        r"예측|전망|예상|앞으로|내일|다음\s*주|이후|넘을지|넘을\s*것|초과할|올라갈|추세|가능성"
        r"|치솟|forecast|tomorrow|흐름|높아질|상승할"
    ),
    "report": re.compile(r"리포트|요약|보고서|일일|브리핑|정리|report|daily"),
}
# 화면 조작은 하지 않는다. 계획기가 화면 부분을 내면 범위 밖 부분으로 바꾼다(단서가 있을 때만).
_SCREEN_CUE = re.compile(
    r"지도|이동|선택|그래프|차트|화면|열어|띄워|하이라이트|골라\s*줘"
    r"|기간.{0,10}바꿔|바꿔\s*(?:보|줘|봐)|바꾸고"
)
SCREEN_NOTE = "화면 조작"
_ALL_STACKS_CUE = re.compile(r"전부|전체|모든|모두|다\s*(?:보|알|줘|합)|굴뚝\s*다|all")
_TIME_CUE = {
    "yesterday": re.compile(r"어제|어저께|어재|yesterday|ㅇㅈ"),
    "today": re.compile(r"오늘|금일|today"),
    "now": re.compile(r"지금|현재|\bnow\b"),
    "hours": re.compile(r"\d+\s*시간|[가-힣]+\s*시간"),
    "date": re.compile(r"\d{1,4}\s*[-./월]\s*\d{1,2}|\d{1,2}\s*일"),
}
OPERATIONS = {"mean", "max", "min", "sum"}


@dataclass
class PlanPart:
    id: str
    agent: str
    intent: str
    stack: dict[str, Any] | None = None
    pollutants: list[str] = field(default_factory=list)
    time: dict[str, Any] | None = None
    operation: str | None = None
    metric: str = "value"
    top_n: int | None = None
    # 순위 방향: asc(낮은 순) | desc(높은 순). 집계 방식(operation)과 따로다
    order: str | None = None
    depends_on: str | None = None  # 첫 번째 의존(실행 판단용)
    depends_all: list[str] = field(default_factory=list)  # 모든 의존(앞선 부분만)
    note: str = ""
    unclear: list[str] = field(default_factory=list)  # 계획기가 확신하지 못한 칸(사람에게 묻는다)
    skipped: bool = False  # 사용자가 "이 부분은 빼고 진행"을 골랐다
    follows_last: bool = False  # 계획기가 직전 조회의 후속이라고 판단했다(빈 칸을 직전 조회로 채움)


class Planner(Protocol):
    def plan(
        self, message: str, now: datetime, *, has_last: bool, last: str | None = None
    ) -> dict[str, Any]:
        """{"parts": [{"id","agent","intent","stack","pollutants","time","operation",
        "metric","top_n","depends_on","note"}, ...]} 를 돌려준다."""
        ...


_SPLIT_FAILED = "질문을 부분으로 나누지 못했습니다. 하나씩 나눠서 질문해 주세요."


class PlanError(ValueError):
    """계획을 쓸 수 없다. 사용자에게 보여 줄 문장을 담는다."""


def _same_region_word(business: str, message: str) -> bool:
    """모델이 지역 이름을 풀어 쓴 것(충북 → 충청북도)은 원문의 지역 말과 같은 지역이면 인정한다."""
    key = sido_key(business)
    tokens = re.findall(r"[가-힣]{2,7}", message)
    return bool(key) and any(sido_key(token) == key for token in tokens)


def _stack(raw: Any, message: str) -> dict[str, Any] | None:
    """모델이 말한 사업장 이름은 원문에 실제로 있을 때만 쓴다(지어낸 이름은 버린다)."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    business = raw.get("business")
    if isinstance(business, str) and len(canon(business)) >= 2:
        if canon(business) in canon(message) or _same_region_word(business, message):
            out["business"] = business
    code = str(raw.get("code") or "")
    if code == "all" or (re.fullmatch(r"\d{1,3}", code) and code in message):
        out["code"] = code
    return out or None


def _time(raw: Any) -> dict[str, Any] | None:
    # 지난주·새벽처럼 지원하지 않는 표현은 '기간 없음'이 아니라 '지원 안 함'으로 남긴다.
    if isinstance(raw, dict) and raw.get("kind") == "other":
        return {"kind": "other"}
    return clean_time(raw)


def _dependencies(raw: Any) -> list[str]:
    """depends_on은 id 하나, 'p1,p2' 문자열, id 목록 모두 받는다."""
    if raw in (None, "", []):
        return []
    if isinstance(raw, str):
        return [d for d in re.split(r"[\s,]+", raw) if d]
    if isinstance(raw, list) and all(isinstance(d, str) for d in raw):
        return [d for d in raw if d]
    raise PlanError(_SPLIT_FAILED)


def _prune_helpers(parts: list[PlanPart], message: str) -> list[PlanPart]:
    """초과 횟수·극값 시각 계산은 굴뚝·물질·기간만 있으면 되므로, 집계를 말하지 않은 값 부분은 뺀다.

    계산 부분이 그 값 부분의 굴뚝·물질·기간을 이어받은 뒤 값 부분을 목록에서 지운다.
    """
    by_id = {p.id: p for p in parts}
    drop: set[str] = set()
    for part in parts:
        if part.metric != "derived" or _calc_kind(part, message) not in ("exceed", "extreme"):
            continue
        for dep in part.depends_all:
            base = by_id.get(dep)
            if base is None or base.operation or base.intent != "aggregate":
                continue
            part.stack = part.stack or base.stack
            part.pollutants = part.pollutants or base.pollutants
            part.time = part.time or base.time
            drop.add(dep)
    if not drop:
        return parts
    kept = [p for p in parts if p.id not in drop]
    for p in kept:
        p.depends_all = [d for d in p.depends_all if d not in drop]
        p.depends_on = p.depends_all[0] if p.depends_all else None
    return kept


def _grounded(part: PlanPart, message: str) -> PlanPart:
    """질문에 단서가 없는 값(직전 대화에서 이어받거나 모델이 지어낸 값)은 비운다."""
    text = fold(message)
    part.pollutants = [p for p in part.pollutants if _POLLUTANT_CUE[p].search(text)]
    # 순위의 집계는 기본값(최댓값)이 있어 말하지 않아도 된다. 그 밖은 질문에 단서가 있어야 한다.
    default_ok = part.intent == "rank" and part.operation == "max"
    if part.operation and not default_ok and not _OPERATION_CUE[part.operation].search(text):
        part.operation = None
    if part.metric != "derived" and _DERIVED_CUE.search(part.note):
        part.metric = "derived"
    elif (
        part.metric == "derived"
        and part.operation
        and part.pollutants
        and part.time
        and not _DERIVED_CUE.search(part.note)
    ):
        part.metric = "value"  # 비교하는 두 값 중 하나: 값은 답하고 계산(차이)은 따로 알린다
    stack = part.stack or {}
    if stack.get("code") == "all" and not _ALL_STACKS_CUE.search(text):
        rest = {k: v for k, v in stack.items() if k != "code"}  # 굴뚝 전부를 말하지 않았다
        part.stack = rest or None
    kind = (part.time or {}).get("kind")
    if kind in _TIME_CUE and not _TIME_CUE[kind].search(text):
        part.time = None
    return part


def parse_plan(raw: Any, message: str) -> list[PlanPart]:
    try:
        return _parse_plan(raw, message)
    except (TypeError, AttributeError, ValueError) as error:
        if isinstance(error, PlanError):
            raise
        raise PlanError(_SPLIT_FAILED) from error


# 예측 결과를 근거로 말한 질문("초과 예측 떴는데")은 예측 부분이 빠져도 준비 중이라고 알린다
_PREDICTION_GIVEN = re.compile(
    r"예측\s*(?:이|은|가|결과|상|떴|나왔|에서|으로|대로|됐|되었|경고|모델|알림)|초과\s*예(?:보|측)|예보"
    r"|(?:초과|넘).{0,6}(?:것\s*같|할\s*듯|할지도|가능성).{0,8}(?:뜨|떴|나오|나왔)"
)


def _ensure_prediction_part(parts: list[PlanPart], message: str) -> list[PlanPart]:
    """예측 결과가 있다고 말하는 질문인데 예측 부분이 없으면 하나 붙인다(조용히 무시하지 않는다)."""
    if any(p.agent == "prediction" for p in parts) or len(parts) >= MAX_PARTS:
        return parts
    if not _PREDICTION_GIVEN.search(fold(message)):
        return parts
    used = {p.id for p in parts}
    n = len(parts) + 1
    while f"p{n}" in used:
        n += 1
    return [
        *parts,
        PlanPart(id=f"p{n}", agent="prediction", intent="predict", note="예측 결과 연결"),
    ]


def _parse_plan(raw: Any, message: str) -> list[PlanPart]:
    if not isinstance(raw, dict) or not isinstance(raw.get("parts"), list) or not raw["parts"]:
        raise PlanError("질문을 부분으로 나누지 못했습니다. 하나씩 나눠서 질문해 주세요.")
    if len(raw["parts"]) > MAX_PARTS:
        raise PlanError(
            f"한 번에 {MAX_PARTS}가지까지만 처리합니다. 질문을 나눠서 다시 입력해 주세요."
        )
    parts: list[PlanPart] = []
    seen: set[str] = set()
    # 순위 부분이 하나뿐이면 계획기가 방향(order)을 빠뜨려도 질문 글에서 읽는다.
    rank_items = sum(
        1 for it in raw["parts"] if isinstance(it, dict) and it.get("intent") == "rank"
    )
    for index, item in enumerate(raw["parts"], 1):
        if not isinstance(item, dict):
            raise PlanError("질문을 부분으로 나누지 못했습니다. 하나씩 나눠서 질문해 주세요.")
        part_id = str(item.get("id") or f"p{index}")
        agent, intent = item.get("agent"), item.get("intent")
        if agent == "ui":  # 화면 조작은 지원하지 않는 요청으로 둔다(계획 전체를 버리지 않는다)
            if not _SCREEN_CUE.search(fold(message)):
                continue
            agent, intent = "blocked", "out_of_scope"
            item = {**item, "note": SCREEN_NOTE}
        elif (
            agent == "blocked"
            and intent == "out_of_scope"
            and _SCREEN_CUE.search(fold(str(item.get("note") or "")))
        ):
            # 계획기가 화면 조작을 직접 범위 밖으로 두면서 note에 "화면 조작 지도 이동"처럼 적었다.
            # 같은 "화면에서 직접 해 주세요" 안내를 쓰도록 note를 맞춘다.
            item = {**item, "note": SCREEN_NOTE}
        if part_id in seen or intent not in AGENT_INTENTS.get(str(agent), set()):
            raise PlanError("질문을 부분으로 나누지 못했습니다. 하나씩 나눠서 질문해 주세요.")
        deps = _dependencies(item.get("depends_on"))
        if any(d not in seen for d in deps):  # 앞선 부분만 가리킬 수 있다(순환·자기참조 차단)
            raise PlanError("부분 사이의 순서를 정하지 못했습니다. 하나씩 나눠서 질문해 주세요.")
        dep = deps[0] if deps else None
        seen.add(part_id)
        operation = item.get("operation")
        top_n = item.get("top_n")
        order = item.get("order") if item.get("order") in ("asc", "desc") else None
        if order is None and intent == "rank" and rank_items == 1:
            order = rank_order(fold(message))
        parts.append(
            PlanPart(
                id=part_id,
                agent=str(agent),
                intent=str(intent),
                stack=_stack(item.get("stack"), message),
                pollutants=sorted(
                    {str(p).lower() for p in item.get("pollutants") or []} & POLLUTANTS
                ),
                time=_time(item.get("time")),
                operation=operation if operation in OPERATIONS else None,
                metric=item["metric"] if item.get("metric") in ("ratio", "derived") else "value",
                top_n=top_n if isinstance(top_n, int) else None,
                order=order,
                depends_on=dep,
                depends_all=deps,
                note=str(item.get("note") or "")[:80],
                follows_last=item.get("follows_last") is True,
                unclear=[
                    u
                    for u in item.get("unclear") or []
                    if u in ("pollutants", "time", "operation")  # 굴뚝 모호함은 인식기가 판단한다
                ]
                if isinstance(item.get("unclear"), list)
                else [],
            )
        )
    kept = [
        p for p in parts if p.agent not in _AGENT_CUE or _AGENT_CUE[p.agent].search(fold(message))
    ]
    dropped = {p.id for p in parts} - {p.id for p in kept}
    for p in kept:
        p.depends_all = [d for d in p.depends_all if d not in dropped]
        p.depends_on = p.depends_all[0] if p.depends_all else None
    parts = _prune_helpers([_grounded(part, message) for part in kept], message)
    return _ensure_prediction_part(parts, message)


def fill_from_last(parts: list[PlanPart], last: dict | None, data: DataSource) -> list[str]:
    """계획기가 직전 조회의 후속이라고 본 데이터 부분의 빈 칸만 직전 조회로 채운다.

    질문에 적힌 칸은 건드리지 않고, 계획기가 확신하지 못한 칸(unclear)도 채우지 않는다.
    채운 칸 이름을 돌려준다(사용자에게 알린다).
    """
    if not last:
        return []
    filled: list[str] = []
    last_stack = last.get("stack") or {}
    for part in parts:
        if not part.follows_last or part.agent not in ("data", "evidence") or part.depends_all:
            continue
        if part.agent == "data" and (
            part.intent not in ("aggregate", "gap") or part.metric == "derived"
        ):
            continue
        stack = part.stack or {}
        if not (stack.get("business") or stack.get("site_id")) and last_stack:
            info = data.get_stack(last_stack.get("stack_key") or "")
            if info is not None:
                part.stack = {"site_id": info.site_id, "code": info.code}
            elif last_stack.get("site_id") or last_stack.get("business"):
                part.stack = dict(last_stack)
            if part.stack:
                filled.append("굴뚝")
        if part.agent != "data":
            continue  # 법령 부분은 굴뚝만 이어받는다(굴뚝 기준·측정값을 붙이려고)
        for name, label in (("pollutants", "물질"), ("time", "기간"), ("operation", "집계")):
            if name in part.unclear or getattr(part, name) or not last.get(name):
                continue
            if name == "operation" and part.intent != "aggregate":
                continue
            setattr(part, name, last[name])
            filled.append(label)
    return list(dict.fromkeys(filled))


def _evidence_facts(
    part: PlanPart,
    plans: dict[str, PlanPart] | None,
    data: DataSource,
    resolver: SiteResolver,
    now: datetime,
) -> tuple[StackFacts | None, tuple[str, ...], str]:
    """법령 부분에 붙일 굴뚝 사실. 같은 부분의 굴뚝, 같은 계획의 데이터 부분 굴뚝 순으로 찾는다.

    굴뚝을 정하지 못하면 일반 규정만 안내하고 그렇다고 알린다(카드로 되묻지 않는다).
    """
    own = part.stack or {}
    siblings = [p for p in (plans or {}).values() if p is not part and p.agent == "data"]
    unresolved = ""
    for candidate in [part, *siblings]:
        stack = candidate.stack or {}
        if not (stack.get("business") or stack.get("site_id")) or stack.get("code") == "all":
            continue
        key, problem = _resolve_stack(candidate, data, resolver, now)
        if key:
            facts = collect_stack_facts(data, key, now)
            drop = tuple(x for x in (stack.get("business"),) if x)
            return facts, drop, ""
        if candidate is part:
            unresolved = "굴뚝을 하나로 정하지 못해 일반 규정만 안내합니다."
    if own and not unresolved and (own.get("business") or own.get("site_id")):
        unresolved = "굴뚝을 하나로 정하지 못해 일반 규정만 안내합니다."
    drop = tuple(x for x in (own.get("business"),) if x)
    return None, drop, unresolved


def _part(part: PlanPart, status: str, notice: str, answer: str | None = None) -> Part:
    return Part(
        part_id=part.id,
        agent=part.agent if part.agent in _PART_AGENTS else "system",  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        label=f"[{AGENT_LABEL.get(part.agent, '안내')}]" + (f" {part.note}" if part.note else ""),
        answer=answer,
        notice=notice or None,
    )


def _resolve_stack(
    part: PlanPart, data: DataSource, resolver: SiteResolver, now: datetime
) -> tuple[str | None, Part | None]:
    """굴뚝 키를 정한다. 확실하지 않으면 이유를 담은 부분을 돌려준다(카드는 아직 쓰지 않는다)."""
    stack = part.stack or {}
    if stack.get("site_id"):  # 사용자가 카드에서 사업장을 골랐다
        return _by_site(part, stack["site_id"], stack.get("code"), data, resolver)
    if stack.get("code") == "all":
        return None, _part(
            part, "UNAVAILABLE", "사업장의 굴뚝 전부를 한 번에 조회하는 기능은 아직 없습니다."
        )
    business = stack.get("business")
    if business and is_group_like(business, resolver, stack.get("code")):
        # 지역·묶음 말: '지원 안 함'이 아니라 왜 하나의 값으로 답하기 어려운지 근거를 알린다
        found_profile = profile_for(business, part.pollutants, part.time, data, resolver, now)
        return None, _part(part, "UNAVAILABLE", explanation(business, found_profile))
    if not business:
        return None, _part(
            part, "NEEDS_INPUT", "어느 굴뚝인지 사업장 이름과 굴뚝 번호가 필요합니다."
        )
    found = resolver.resolve(business)
    if found.outcome == "NONE":
        return None, _part(part, "UNAVAILABLE", "등록되지 않은 사업장입니다.")
    if found.outcome == "CARD":
        names = ", ".join(sorted({s.business for s in found.sites})[:3])
        return None, _part(part, "NEEDS_INPUT", f"사업장이 하나로 정해지지 않았습니다: {names}")
    site = found.sites[0]
    infos = [s for s in data.list_stacks() if s.site_id == site.site_id]
    code = stack.get("code") or (
        found.numbers[0] if len(found.numbers) == 1 and found.numbers[0] in site.codes else None
    )
    if code:
        match = [s for s in infos if s.code == str(code)]
        if match:
            return match[0].stack_key, None
        return None, _part(
            part, "NEEDS_INPUT", "그 번호의 굴뚝이 없습니다. 굴뚝 번호를 확인해 주세요."
        )
    if len(infos) == 1:
        return infos[0].stack_key, None
    codes = ", ".join(sorted((s.code for s in infos), key=lambda c: (len(c), c))[:8])
    return None, _part(part, "NEEDS_INPUT", f"굴뚝 번호가 필요합니다 ({codes})")


def _by_site(
    part: PlanPart, site_id: str, code: Any, data: DataSource, resolver: SiteResolver
) -> tuple[str | None, Part | None]:
    infos = [s for s in data.list_stacks() if s.site_id == site_id]
    if code and code != "all":
        match = [s for s in infos if s.code == str(code)]
        if match:
            return match[0].stack_key, None
        return None, _part(part, "NEEDS_INPUT", "그 번호의 굴뚝이 없습니다.")
    if len(infos) == 1:
        return infos[0].stack_key, None
    return None, _part(part, "NEEDS_INPUT", "굴뚝 번호가 필요합니다.")


def _inherit(
    part: PlanPart, before: Part, before_plan: PlanPart | None, data: DataSource
) -> Part | None:
    """앞 순위 부분의 1등 굴뚝을 이어받는다. 이어받을 수 없으면 이유를 담은 부분을 돌려준다.

    '그 굴뚝·거기'는 앞 조회와 같은 물질·기간을 가리키므로 비어 있으면 앞 부분의 것을 쓴다.
    """
    top = before.numbers[0] if before.numbers else None
    if part.intent not in ("aggregate", "gap") or top is None or not top.stack_key:
        return _part(
            part, "UNAVAILABLE", "앞 결과를 이어받아 조회하는 기능은 순위 다음 조회만 지원합니다."
        )
    info = data.get_stack(top.stack_key)
    if info is None:
        return _part(part, "UNAVAILABLE", "앞 결과의 굴뚝을 찾지 못했습니다.")
    part.stack = {"site_id": info.site_id, "code": info.code}
    part.depends_on = None  # 이어받기를 마쳤으니 이후는 일반 조회처럼 처리한다
    if before_plan is not None:
        part.pollutants = part.pollutants or before_plan.pollutants
        part.time = part.time or before_plan.time
        if before_plan.intent == "rank":  # "1등 굴뚝 값"은 순위를 매긴 그 집계값을 가리킨다
            part.operation = part.operation or before_plan.operation or "max"
    return None


# ── 파생 계산: 이미 가진 값이나 같은 굴뚝의 관측으로 계산하는 부분 ─────────────────────
_CALC_EXCEED = re.compile(r"넘은|넘었|초과|연속|넘는")
_CALC_EXTREME = re.compile(r"시각|언제|몇\s*시|시간대")
_CALC_DIFF = re.compile(
    r"차이|증감|올랐|내렸|떨어졌|변화율|얼마나\s*(?:늘|줄|올|내)|비교|대비|벌어"
)


def _calc_kind(part: PlanPart, question: str) -> str | None:
    question = fold(question)
    text = f"{part.note} {question}"
    if _CALC_EXCEED.search(part.note) or (part.note == "" and _CALC_EXCEED.search(question)):
        return "exceed"
    if _CALC_EXTREME.search(text) and re.search(r"높|낮|제일|가장|최고|최대|최소|최저", text):
        return "extreme"
    if _CALC_DIFF.search(part.note) or len(part.depends_all) >= 2:
        return "diff"
    return None


def _context(part: PlanPart, plans: dict[str, PlanPart] | None) -> None:
    """계산 부분이 굴뚝·물질·기간을 말하지 않았으면 의존하는 값 부분의 것을 쓴다."""
    for dep in part.depends_all:
        before = plans.get(dep) if plans else None
        if before is None or before.intent == "rank":
            continue
        part.stack = part.stack or before.stack
        part.pollutants = part.pollutants or before.pollutants
        part.time = part.time or before.time
        return


def _run_calc(
    kind: str,
    part: PlanPart,
    data: DataSource,
    resolver: SiteResolver,
    now: datetime,
    done: dict[str, Part],
    plans: dict[str, PlanPart] | None,
    question: str,
) -> Part:
    if kind == "diff":
        values = [done[d] for d in part.depends_all if d in done and done[d].status == "DONE"]
        if len(values) < 2:
            return _part(part, "UNAVAILABLE", "견줄 두 값이 모두 있어야 차이를 계산합니다.")
        return run_diff(values[0], values[1]).model_copy(update={"part_id": part.id})
    _context(part, plans)
    if not part.pollutants or len(part.pollutants) != 1 or not part.time:
        return _part(part, "NEEDS_INPUT", "물질 한 가지와 기간이 필요합니다.")
    stack_key, problem = _resolve_stack(part, data, resolver, now)
    if problem:
        return problem
    try:
        period = resolve_period(part.time, now)  # type: ignore[arg-type]
    except UnsupportedPeriod as error:
        return _part(part, "UNAVAILABLE", str(error))
    item = part.pollutants[0]
    if kind == "exceed":
        result = run_exceedance(data, stack_key, item, period, data.as_of())  # type: ignore[arg-type]
    else:
        low = re.search(r"낮|최소|최저", f"{part.note} {question}") is not None
        op = part.operation or ("min" if low else "max")
        result = run_extreme_time(data, stack_key, item, op, period, data.as_of())  # type: ignore[arg-type]
    return result.model_copy(update={"part_id": part.id})


def _site_list(
    part: PlanPart, data: DataSource, resolver: SiteResolver, now: datetime
) -> Part | None:
    """'굴뚝 전부'는 사업장의 굴뚝별 값을 나란히 보여 준다. 사업장이 정해지지 않으면 None."""
    found = resolver.resolve((part.stack or {}).get("business") or "")
    if found.outcome != "AUTO":
        return None
    missing = [n for n in ("pollutants", "time", "operation") if not getattr(part, n)]
    if missing:
        return _part(part, "NEEDS_INPUT", "빠진 정보: " + ", ".join(missing))
    try:
        period = resolve_period(part.time, now)  # type: ignore[arg-type]
    except UnsupportedPeriod as error:
        return _part(part, "UNAVAILABLE", str(error))
    result = run_site_stacks(
        data,
        found.sites[0].site_id,
        part.pollutants[0],
        part.operation,  # type: ignore[arg-type]
        part.metric,
        period,
        data.as_of(),
    )
    return result.model_copy(update={"part_id": part.id})


def _missing(part: PlanPart) -> list[str]:
    names = {"pollutants": "물질", "time": "기간", "operation": "집계 방식"}
    need = [n for n in REQUIRED.get(part.intent, ()) if n != "stack"]
    if part.intent == "rank":
        return [names[n] for n in ("pollutants", "time") if n in need and not getattr(part, n)]
    return [names[n] for n in need if not getattr(part, n)]


def run_part(
    part: PlanPart,
    data: DataSource,
    resolver: SiteResolver,
    now: datetime,
    done: dict[str, Part],
    plans: dict[str, PlanPart] | None = None,
    question: str = "",
    evidence: EvidenceAgent | None = None,
) -> Part:
    if part.skipped:
        return _part(part, "SKIPPED", "사용자가 이 부분을 빼고 진행하도록 했습니다.")
    if part.intent == "out_of_scope":
        if part.note == SCREEN_NOTE:
            return _part(part, "UNAVAILABLE", "화면 조작은 하지 않습니다. 화면에서 직접 해 주세요.")
        return _part(part, "UNAVAILABLE", "굴뚝 측정값과 관련 없는 요청이라 도와드릴 수 없습니다.")
    if part.agent == "report":
        try:
            period = resolve_period(part.time or {"kind": "yesterday"}, now)  # type: ignore[arg-type]
        except UnsupportedPeriod as error:
            return _part(part, "UNAVAILABLE", str(error))
        return run_report(data, period, data.as_of()).model_copy(
            update={"part_id": part.id, "label": f"[요약] {part.note}".strip()}
        )
    if part.agent == "evidence" and evidence is not None:
        facts, drop, unresolved = _evidence_facts(part, plans, data, resolver, now)
        if getattr(evidence, "summarizer", None) is not None:
            # 요약 모드: 질문 전체를 요약기가 읽는다(부분 설명은 이름표로만 쓴다)
            found = evidence.answer(question or part.note, part.id, facts=facts, drop=drop)
        else:
            # 원문 발췌 모드: 부분 설명으로 먼저 찾고, 못 찾으면 질문 전체로 다시 찾는다
            found = evidence.answer(part.note or question, part.id, facts=facts, drop=drop)
            if found.status != "DONE" and part.note and question:
                found = evidence.answer(question, part.id, facts=facts, drop=drop)
        update: dict[str, Any] = {"label": f"[규정] {part.note}".strip()}
        if unresolved:
            update["notice"] = " ".join(x for x in (found.notice, unresolved) if x)
        return found.model_copy(update=update)
    if part.agent != "data":
        return _part(part, "UNAVAILABLE", UNSUPPORTED_TEXT[part.agent])
    if part.metric == "derived" and not part.skipped:
        kind = _calc_kind(part, question)
        if kind:
            return _run_calc(kind, part, data, resolver, now, done, plans, question)
        return _part(
            part,
            "UNAVAILABLE",
            "값을 가공하는 계산(이상치 제외·보정·반올림 등)은 아직 하지 않습니다.",
        )
    if part.depends_on and done[part.depends_on].status != "DONE":
        return _part(part, "SKIPPED", "앞 부분이 끝나지 않아 건너뜁니다.")
    if part.depends_on:
        before_plan = plans.get(part.depends_on) if plans else None
        inherited = _inherit(part, done[part.depends_on], before_plan, data)
        if inherited is not None:
            return inherited
    if part.intent == "freshness":
        return run_freshness(data, now).model_copy(update={"part_id": part.id})
    if part.metric == "derived":
        return _part(
            part,
            "UNAVAILABLE",
            "증감·차이·초과 횟수·가장 높았던 시각 같은 계산은 아직 하지 않습니다.",
        )
    stack = part.stack or {}
    if part.intent == "aggregate" and stack.get("code") == "all" and stack.get("business"):
        listed = _site_list(part, data, resolver, now)
        if listed is not None:
            return listed
    if part.intent in ("aggregate", "gap") and not (stack.get("business") or stack.get("site_id")):
        return _part(  # 굴뚝을 모르면 기간·집계를 따지기 전에 이것부터 알린다
            part, "NEEDS_INPUT", "어느 굴뚝인지 사업장 이름과 굴뚝 번호가 필요합니다."
        )
    missing = _missing(part)
    if missing:
        return _part(part, "NEEDS_INPUT", f"빠진 정보: {', '.join(missing)}")
    if part.intent == "rank" and len(part.pollutants) != 1:
        return _part(part, "NEEDS_INPUT", "순위는 물질 한 가지씩만 볼 수 있습니다.")
    command: dict[str, Any] = {
        "intent": part.intent,
        "pollutants": part.pollutants,
        "time": part.time,
        "operation": part.operation or ("max" if part.intent == "rank" else None),
        "metric": part.metric,
    }
    if part.intent in ("aggregate", "gap"):
        stack_key, problem = _resolve_stack(part, data, resolver, now)
        if problem:
            return problem
        command["stack"] = {"stack_key": stack_key}
        if part.intent == "aggregate" and not part.operation:
            return _part(part, "NEEDS_INPUT", "빠진 정보: 집계 방식")
    else:
        command["top_n"] = max(1, min(part.top_n or DEFAULT_TOP_N, MAX_TOP_N))
        if part.order:
            command["order"] = part.order
        stack = part.stack or {}
        scope = stack.get("region") or (
            stack.get("business")
            if is_group_like(stack.get("business") or "", resolver, stack.get("code"))
            else None
        )
        sites = resolver.sites_in_region(scope) if scope else []
        if scope and sites:  # 지역 안 순위
            command["site_ids"] = [s.site_id for s in sites]
            command["scope_label"] = f"{scope} 안에서"
    try:
        period = resolve_period(part.time, now)  # type: ignore[arg-type]
    except UnsupportedPeriod as error:
        return _part(part, "UNAVAILABLE", str(error))
    handler = {"aggregate": run_aggregate, "rank": run_rank, "gap": run_gap}[part.intent]
    result, _failed = handler(data, command, period, data.as_of())  # type: ignore[arg-type]
    result = result.model_copy(update={"part_id": part.id})
    return result


def run_plan(
    parts: list[PlanPart],
    data: DataSource,
    resolver: SiteResolver,
    now: datetime,
    question: str = "",
    evidence: EvidenceAgent | None = None,
) -> list[Part]:
    done: dict[str, Part] = {}
    plans = {part.id: part for part in parts}
    out: list[Part] = []
    for part in parts:
        result = run_part(part, data, resolver, now, done, plans, question, evidence)
        done[part.id] = result
        out.append(result)
    return out
