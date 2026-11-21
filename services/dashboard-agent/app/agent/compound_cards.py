"""복합 질문의 되묻기 카드.

원칙: 모호하거나 단정할 수 없는 부분은 AI가 마음대로 채우지 않고 사람에게 묻는다.
카드의 문구와 선택지는 코드가 정한다(모델이 쓰지 않는다). 모호하게 말한 사람도 카드에 답하면
원하는 조회를 얻을 수 있어야 하므로, 선택지는 지금 실제로 실행할 수 있는 것만 내놓는다.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from app.agent.compound import PlanPart, _calc_kind
from app.agent.names import Site, SiteResolver
from app.agent.region import explanation, is_group_like, profile_for
from app.agent.slots import OPERATION_LABEL, UnsupportedPeriod, resolve_period
from app.agent.tools import DataSource

SKIP_LABEL = "이 부분은 빼고 진행"
MAX_SITE_OPTIONS = 3
MAX_CODE_OPTIONS = 8


def _opt(option_id: str, label: str, part_id: str, **change: Any) -> dict:
    return {
        "id": option_id,
        "label": label,
        "skip_part": False,
        "edit": {"part": part_id, "set": change},
    }


def _card(kind: str, part: PlanPart, message: str, options: list[dict]) -> dict:
    heading = f"[{part.note}] " if part.note else f"[{part.id}] "
    skip = {
        "id": "skip",
        "label": SKIP_LABEL,
        "skip_part": True,
        "edit": {"part": part.id, "skip": True},
    }
    return {
        "card_id": uuid.uuid4().hex[:12],
        "kind": kind,
        "message": heading + message,
        "options": [*options, skip],
    }


def _site_label(site: Site) -> str:
    place = " ".join(p for p in (site.region, site.sigungu) if p)
    return f"{site.business} · {place}" if place else site.business


def _code_card(part: PlanPart, site: Site, message: str) -> dict:
    codes = sorted(site.codes, key=lambda c: (len(c), c))[:MAX_CODE_OPTIONS]
    options = [
        _opt(f"code-{c}", f"굴뚝 {c}", part.id, stack={"site_id": site.site_id, "code": c})
        for c in codes
    ]
    return _card("STACK_CODE", part, message, options)


def _site_card(part: PlanPart, sites: list[Site], code: Any = None) -> dict:
    options = [
        _opt(
            s.site_id,
            _site_label(s),
            part.id,
            stack={"site_id": s.site_id, **({"code": code} if code else {})},
        )
        for s in sites[:MAX_SITE_OPTIONS]
    ]
    return _card("STACK_CANDIDATES", part, "어느 사업장인가요?", options)


def _region_card(
    part: PlanPart, business: str, data: DataSource, resolver: SiteResolver, now: datetime
) -> dict:
    sites = resolver.sites_in_region(business)
    found = profile_for(business, part.pollutants, part.time, data, resolver, now)
    options: list[dict] = []
    if 0 < len(sites) <= MAX_SITE_OPTIONS:
        options += [
            _opt(s.site_id, _site_label(s), part.id, stack={"site_id": s.site_id}) for s in sites
        ]
    if sites:
        options.append(
            _opt(
                "region-rank",
                "이 지역 안에서 순위로 보기",
                part.id,
                intent="rank",
                stack={"region": business},
            )
        )
    options.append(_opt("national-rank", "전국 순위로 보기", part.id, intent="rank", stack=None))
    options.append(_opt("retype", "사업장 이름을 직접 말씀드릴게요", part.id, stack=None))
    return _card("SCOPE", part, explanation(business, found) + " 무엇을 볼까요?", options)


def _stack_question(part: PlanPart, data: DataSource, resolver: SiteResolver) -> dict | None:
    stack = part.stack or {}
    site_by_id = {s.site_id: s for s in resolver.sites}
    if stack.get("site_id"):
        site = site_by_id.get(stack["site_id"])
        if site is None:
            return None
        code = stack.get("code")
        if code and code != "all" and str(code) in site.codes:
            return None
        if len(site.codes) == 1 and not (code and code != "all"):
            return None
        message = (
            "그 번호의 굴뚝이 없습니다. 굴뚝 번호를 골라 주세요."
            if code and code != "all"
            else "굴뚝 번호를 골라 주세요."
        )
        return _code_card(part, site, message)
    business = stack.get("business")
    if not business or is_group_like(business, resolver, stack.get("code")):
        return None  # 지역·묶음 말은 물질·기간을 먼저 정한 뒤 따로 묻는다
    found = resolver.resolve(business)
    if found.outcome == "NONE":
        return None
    code = stack.get("code")
    if found.outcome == "CARD":
        return _site_card(part, list(found.sites), code if code != "all" else None)
    site = found.sites[0]
    if code == "all":
        return None  # 사업장이 정해졌으니 굴뚝별 값을 나란히 보여 준다(실행 단계)
    chosen = code or (found.numbers[0] if len(found.numbers) == 1 else None)
    if chosen and str(chosen) in site.codes:
        return None
    if not chosen and len(site.codes) == 1:
        return None
    message = "굴뚝 번호를 골라 주세요."
    if chosen:
        message = "그 번호의 굴뚝이 없습니다. 굴뚝 번호를 골라 주세요."
    return _code_card(part, site, message)


def _time_question(part: PlanPart, now: datetime) -> dict | None:
    kind = (part.time or {}).get("kind")
    if part.time is None or "time" in part.unclear:
        return _card("TIME", part, "어느 기간을 볼까요?", _time_options(part))
    if kind in ("other", "now"):
        return _card(
            "PERIOD",
            part,
            "말씀하신 기간은 아직 지원하지 않습니다. 이렇게 볼까요?",
            _time_options(part, hours=True),
        )
    try:
        resolve_period(part.time, now)  # type: ignore[arg-type]
    except UnsupportedPeriod:
        message = "그 기간은 지원하지 않습니다. 이렇게 볼까요?"
        return _card("PERIOD", part, message, _time_options(part, hours=True))
    return None


def _time_options(part: PlanPart, hours: bool = False) -> list[dict]:
    options = [
        _opt("yesterday", "어제", part.id, time={"kind": "yesterday"}),
        _opt("today", "오늘 현재까지", part.id, time={"kind": "today"}),
    ]
    if hours:
        hours24 = {"kind": "hours", "value": 24}
        options.append(_opt("hours-24", "최근 24시간", part.id, time=hours24))
    return options


def _pollutant_question(part: PlanPart) -> dict | None:
    single = part.intent == "rank"
    wrong_count = single and len(part.pollutants) != 1
    if part.pollutants and not wrong_count and "pollutants" not in part.unclear:
        return None
    options = [
        _opt("nox", "NOx", part.id, pollutants=["nox"]),
        _opt("sox", "SOx", part.id, pollutants=["sox"]),
    ]
    if not single:
        options.append(_opt("both", "NOx와 SOx 모두", part.id, pollutants=["nox", "sox"]))
    return _card("POLLUTANT", part, "어느 물질을 볼까요?", options)


_UNSUPPORTED_OPERATION = re.compile(r"중앙값|표준편차|분산|백분위|퍼센타일|최빈")


def _operation_question(part: PlanPart, message: str = "") -> dict | None:
    derived = part.metric == "derived"
    if derived and _calc_kind(part, message):
        return None  # 초과 횟수·극값 시각·차이는 지원하는 계산이라 집계 방식을 묻지 않는다
    if part.intent != "aggregate" or (
        part.operation and "operation" not in part.unclear and not derived
    ):
        return None
    options = [
        _opt(op, label, part.id, operation=op)
        for op, label in OPERATION_LABEL.items()
        if op != "sum"
    ]
    asked = _UNSUPPORTED_OPERATION.search(message)
    if derived:
        text = (
            "말씀하신 계산(증감·차이·초과 횟수·가장 높았던 시각 등)은 아직 하지 않습니다. "
            "대신 볼 수 있는 값을 골라 주세요."
        )
    elif asked:
        text = f"'{asked.group(0)}'은(는) 아직 지원하지 않습니다. 이 중에서 골라 주세요."
    else:
        text = "어떤 값을 볼까요?"
    return _card("OPERATION", part, text, options)


def next_question(
    parts: list[PlanPart],
    data: DataSource,
    resolver: SiteResolver,
    now: datetime,
    message: str = "",
) -> tuple[PlanPart, dict] | None:
    """아직 사람에게 물어야 할 첫 번째 부분과 카드를 돌려준다. 없으면 None."""
    for part in parts:
        if part.skipped or part.agent != "data" or part.depends_on or part.intent == "freshness":
            continue
        business = (part.stack or {}).get("business")
        group = (
            part.intent in ("aggregate", "gap")
            and bool(business)
            and is_group_like(business, resolver, (part.stack or {}).get("code"))
        )
        has_stack = bool((part.stack or {}).get("business") or (part.stack or {}).get("site_id"))
        if part.intent in ("aggregate", "gap") and not has_stack:
            continue  # 굴뚝을 모르면 다른 칸을 묻기 전에 실행 단계가 굴뚝이 필요하다고 알린다
        if part.intent in ("aggregate", "gap") and not group:
            card = _stack_question(part, data, resolver)
            if card:
                return part, card
        card = _pollutant_question(part) or _time_question(part, now)
        if card:
            return part, card
        if group:  # 물질·기간이 정해진 뒤에 지역 프로파일 근거와 함께 묻는다
            return part, _region_card(part, business, data, resolver, now)
        card = _operation_question(part, message)
        if card:
            return part, card
    return None


def apply_edit(parts: list[PlanPart], edit: dict[str, Any]) -> None:
    """카드 답을 계획에 반영한다. 답한 칸은 '확신 없음' 표시에서 뺀다."""
    for part in parts:
        if part.id != edit.get("part"):
            continue
        if edit.get("skip"):
            part.skipped = True
            return
        for key, value in (edit.get("set") or {}).items():
            if key == "intent":
                part.intent = value
            elif key in ("stack", "pollutants", "time", "operation"):
                setattr(part, key, value)
                if key == "operation" and part.metric == "derived":
                    part.metric = "value"  # 사용자가 대신 볼 값을 골랐다
                if key in part.unclear:
                    part.unclear.remove(key)
        return
