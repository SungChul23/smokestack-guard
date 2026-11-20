"""LangGraph 그래프: 이해 → 판정 → (카드 중단·재개) → 도구 → 응답.

흐름은 코드가 정한다. 모델(해석기)은 질문에서 칸 값만 뽑는다. 카드 문구와 선택지는 코드가 정한다.
카드는 `interrupt`로 멈추고, 사용자가 고르면 같은 대화(thread)에서 이어서 실행한다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agent.compound import (
    PlanError,
    Planner,
    PlanPart,
    fill_from_last,
    parse_plan,
    run_plan,
)
from app.agent.compound_cards import apply_edit as apply_plan_edit
from app.agent.compound_cards import next_question
from app.agent.contract import Part
from app.agent.evidence import EvidenceAgent
from app.agent.extractor import Extractor
from app.agent.fold import fold
from app.agent.guard import BLOCKED_MESSAGE, SMALLTALK_REPLIES, TOO_LONG_MESSAGE, check_input
from app.agent.handlers import run_aggregate, run_freshness, run_gap, run_rank
from app.agent.names import Site, SiteResolver, stack_code_from
from app.agent.region import is_group_like
from app.agent.router import (
    asks_all_stacks,
    complex_reasons,
    law_only,
    other_reasons,
    report_only,
    unexplained_words,
)
from app.agent.slots import (
    DEFAULT_TOP_N,
    INTENTS,
    KST,
    MAX_TOP_N,
    OPERATION_LABEL,
    Command,
    UnsupportedPeriod,
    merge_command,
    rank_order,
    resolve_period,
)
from app.agent.tools import DataSource, StackInfo

# 법령 전용 경로에서 예측·리포트 요청이 섞이면 일부가 사라진다: 계획기로 보낸다
_LAW_MIXED = re.compile(r"예측|전망|예상|앞으로|리포트|브리핑|일일")
_LAW_FOLLOW = re.compile(r"\s*(?:그럼|그러면|그리고|그건|그것|거기|그\s*굴뚝)")
FOCUS_TTL = timedelta(minutes=15)  # 직전 조회를 이어받는 시간 (현재 로컬 라우터와 같다)
MAX_CARDS = 6
MAX_RETYPES = 2  # 이름을 못 찾은 횟수("이 중에 없음" 포함). 2번째 실패에서 지도 선택을 안내한다
SKIP_LABEL = "이 부분은 빼고 진행"
NONE_LABEL = "이 중에 없음"


class State(TypedDict, total=False):
    message: str
    now: str
    context: dict
    extracted: dict
    command: Command
    last_command: dict | None
    card: dict | None
    cards_asked: int
    skipped: bool
    final: str | None  # 더 진행하지 않고 끝내는 이유
    plan: list[dict]  # 복합 질문의 계획(부분 목록). 카드 답을 받으며 채워진다
    pending: dict | None  # "이 중에 없음" 뒤 사업장 이름을 다시 받는 중: command, at, tries
    retry: int  # 이번 입력이 사업장 이름을 다시 받은 몇 번째 시도인지(0 = 새 질문)
    parts: list[dict]
    notices: list[str]
    route: str
    reason: str
    data_as_of: str | None


# ── 카드 (문구와 선택지는 코드가 정한다) ─────────────────────────────────
def _card(kind: str, message: str, options: list[dict], *, with_none: bool = False) -> dict:
    tail = []
    if with_none:
        tail.append({"id": "none", "label": NONE_LABEL, "skip_part": False, "edit": {}})
    tail.append({"id": "skip", "label": SKIP_LABEL, "skip_part": True, "edit": {}})
    return {
        "card_id": uuid.uuid4().hex[:12],
        "kind": kind,
        "message": message,
        "options": [*options, *tail],
    }


def _option(option_id: str, label: str, edit: dict) -> dict:
    return {"id": option_id, "label": label, "skip_part": False, "edit": edit}


def card_time() -> dict:
    return _card(
        "TIME",
        "어느 기간을 볼까요?",
        [
            _option("yesterday", "어제", {"time": {"kind": "yesterday"}}),
            _option("today", "오늘 현재까지", {"time": {"kind": "today"}}),
        ],
    )


def card_pollutant(*, single: bool = False) -> dict:
    options = [
        _option("nox", "NOx", {"pollutants": ["nox"]}),
        _option("sox", "SOx", {"pollutants": ["sox"]}),
    ]
    if not single:
        options.append(_option("both", "NOx와 SOx 모두", {"pollutants": ["nox", "sox"]}))
    return _card("POLLUTANT", "어느 물질을 볼까요?", options)


_UNSUPPORTED_PERIOD = re.compile(
    r"지난\s*주|이번\s*주|지난\s*달|이번\s*달|그저께|엊그제|새벽|어젯밤|(?:최근|지난)\s*(?:[4-9]|\d{2,})\s*일"
)
_UNSUPPORTED_OPERATION = re.compile(r"중앙값|표준편차|분산|백분위|퍼센타일|최빈")


def card_period(message: str = "") -> dict:
    return _card(
        "PERIOD",
        "말씀하신 기간은 아직 지원하지 않습니다. 이렇게 볼까요?",
        [
            _option("yesterday", "어제", {"time": {"kind": "yesterday"}}),
            _option("today", "오늘 현재까지", {"time": {"kind": "today"}}),
            _option("hours-24", "최근 24시간", {"time": {"kind": "hours", "value": 24}}),
        ],
    )


def card_operation(message: str = "") -> dict:
    asked = _UNSUPPORTED_OPERATION.search(message)
    text = (
        f"'{asked.group(0)}'은(는) 아직 지원하지 않습니다. 이 중에서 골라 주세요."
        if asked
        else "어떤 값을 볼까요?"
    )
    return _card(
        "OPERATION",
        text,
        [
            _option(op, label, {"operation": op})
            for op, label in OPERATION_LABEL.items()
            if op != "sum"
        ],
    )


def card_stack_code(infos: list[StackInfo], message: str = "굴뚝 번호를 골라 주세요.") -> dict:
    ordered = sorted(infos, key=lambda s: (len(s.code), s.code))[:8]
    return _card(
        "STACK_CODE",
        message,
        [
            _option(s.stack_key, f"굴뚝 {s.code}", {"stack": {"stack_key": s.stack_key}})
            for s in ordered
        ],
        with_none=True,
    )


def card_stack_sites(infos: list[Any], message: str = "어느 사업장인가요?") -> dict:
    sites: dict[str, Any] = {}
    for info in infos:
        sites.setdefault(info.site_id, info)
    options = [
        _option(
            info.site_id,
            _site_label(info),
            {"stack": {"site_id": info.site_id}},
        )
        for info in list(sites.values())[:3]
    ]
    return _card("STACK_CANDIDATES", message, options, with_none=True)


def _site_label(info: Any) -> str:
    place = " ".join(p for p in (info.region, getattr(info, "sigungu", "")) if p)
    return f"{info.business} · {place}" if place else info.business


def apply_edit(command: Command, edit: dict) -> Command:
    result: Command = {**command}  # type: ignore[assignment]
    for key, value in edit.items():
        if key == "stack":
            result["stack"] = {**(result.get("stack") or {}), **value}
        else:
            result[key] = value  # type: ignore[literal-required]
    return result


def public_card(card: dict) -> dict:
    return {
        "card_id": card["card_id"],
        "kind": card["kind"],
        "message": card["message"],
        "options": [
            {"id": o["id"], "label": o["label"], "skip_part": o["skip_part"]}
            for o in card["options"]
        ],
    }


# ── 그래프 ────────────────────────────────────────────────────────────
def _parse_now(state: State) -> datetime:
    return datetime.fromisoformat(state["now"]).astimezone(KST)


def _focus_alive(last: dict | None, now: datetime) -> bool:
    if not last:
        return False
    return now - datetime.fromisoformat(last["delivered_at"]) <= FOCUS_TTL


def sites_from(data: DataSource) -> list[Site]:
    """굴뚝 목록에서 사업장 목록을 만든다(사업장별 굴뚝 번호 포함)."""
    grouped: dict[str, list[StackInfo]] = {}
    for stack in data.list_stacks():
        grouped.setdefault(stack.site_id, []).append(stack)
    return [
        Site(
            site_id,
            items[0].business,
            items[0].region,
            items[0].sigungu,
            tuple(sorted((s.code for s in items), key=lambda c: (len(c), c))),
        )
        for site_id, items in grouped.items()
    ]


def _time_text(time: dict | None) -> str:
    if not time:
        return "없음"
    kind = time.get("kind")
    return f"{kind} {time['value']}" if time.get("value") else str(kind)


def build_graph(
    extractor: Extractor,
    data: DataSource,
    checkpointer: Any,
    resolver: SiteResolver | None = None,
    planner: Planner | None = None,
    evidence: EvidenceAgent | None = None,
):
    resolver = resolver or SiteResolver(sites_from(data))
    site_by_id = {s.site_id: s for s in resolver.sites}

    def reset() -> dict[str, Any]:
        return {
            "cards_asked": 0,
            "skipped": False,
            "final": None,
            "plan": [],
            "retry": 0,
            "card": None,
            "parts": [],
            "notices": [],
            "data_as_of": None,
        }

    def guard(state: State) -> dict:
        result = check_input(state["message"])
        base = {**reset(), "message": result.text}  # 개인정보를 가린 문장만 상태에 남긴다
        if result.action == "BLOCK":
            final = "too_long" if result.reason == "TOO_LONG" else "blocked"
            return {**base, "route": "BLOCKED", "reason": result.reason, "final": final}
        if result.action == "SMALLTALK":
            reply = Part(
                part_id="p1",
                agent="system",
                status="DONE",
                label="안내",
                answer=SMALLTALK_REPLIES[result.reason],
            ).model_dump()
            return {
                **base,
                "parts": [reply],
                "route": "SMALLTALK",
                "reason": result.reason,
                "final": "smalltalk",
            }
        return base

    def understand(state: State) -> dict:
        now = _parse_now(state)
        last = state.get("last_command")
        alive = _focus_alive(last, now)
        extracted = extractor.extract(state["message"], now, has_last=alive)
        pending = state.get("pending")
        if pending and now - datetime.fromisoformat(pending["at"]) <= FOCUS_TTL:
            # 새 질문(물질·집계·기간이 있는 말)이 아니면 사업장 이름을 다시 말한 것으로 읽는다.
            if not (
                extracted.get("pollutants") or extracted.get("operation") or extracted.get("time")
            ):
                command = {
                    **pending["command"],
                    "stack": extracted.get("stack") or {"business": state["message"]},
                }
                return {
                    "extracted": extracted,
                    "command": command,
                    "route": "DATA",
                    "reason": "READY",
                    "retry": pending["tries"],
                    "pending": None,
                }
        intent = extracted.get("intent")
        if intent not in INTENTS:
            return {
                "pending": None,
                "extracted": extracted,
                "route": "OUT_OF_SCOPE",
                "reason": "NOT_DATA_QUERY",
                "final": "scope",
            }
        base_command = last["command"] if alive and last else None
        patch = extracted.get("patch") if alive else None
        command = merge_command(base_command, extracted, patch)
        if intent == "aggregate" and patch is not None and base_command:
            # '그럼 SOx는?' 같은 후속 질문은 직전 질문의 유형(순위·결측 이유 포함)을 이어받는다.
            intent = base_command.get("intent") or "aggregate"
        notices: list[str] = []
        code_only = extracted.get("code_only")
        if code_only and base_command and alive:
            # "3번은?"처럼 사업장 이름 없이 번호만 말하면 직전 조회의 사업장에서 번호만 바꾼다
            base_stack = base_command.get("stack") or {}
            info = data.get_stack(base_stack.get("stack_key") or "")
            site_id = base_stack.get("site_id") or (info.site_id if info else None)
            if not (site_id and site_id in site_by_id):
                # 직전 조회에 사업장이 없으면(전국 순위 등) 번호가 무엇을 뜻하는지 알 수 없다
                return {
                    "pending": None,
                    "extracted": extracted,
                    "route": "DATA",
                    "reason": "NEED_STACK",
                    "final": "need_stack",
                }
            if site_id and site_id in site_by_id:
                command["stack"] = {"site_id": site_id, "code": str(code_only)}
                notices.append(
                    f"사업장 이름이 없어 직전 조회의 {site_by_id[site_id].business}에서 "
                    f"굴뚝 {code_only}번으로 바꿔 조회합니다."
                )
        command["intent"] = intent
        if intent == "rank":
            top_n = extracted.get("top_n") or command.get("top_n") or DEFAULT_TOP_N
            command["top_n"] = max(1, min(int(top_n), MAX_TOP_N))
            command["operation"] = extracted.get("operation") or command.get("operation") or "max"
            order = (
                extracted.get("order") or rank_order(fold(state["message"])) or command.get("order")
            )
            if order:
                command["order"] = order
        selected = (state.get("context") or {}).get("selectedStackId")
        if (
            intent in ("aggregate", "gap")
            and not command.get("stack")
            and selected
            and data.get_stack(selected)
        ):
            command["stack"] = {"stack_key": selected}
        update: dict[str, Any] = {
            "pending": None,
            "extracted": extracted,
            "command": command,
            "route": "DATA",
            "reason": "READY",
        }
        if notices:
            update["notices"] = notices
        return update

    def resolve_stack(command: Command, stack: dict, notes: list[str]) -> dict:
        """지역 → 사업장 → 굴뚝 순서로 굴뚝을 정한다. 확실하지 않으면 카드로 묻는다."""
        site = site_by_id.get(stack.get("site_id") or "")
        numbers: tuple[str, ...] = ()
        if site is None:
            text = stack.get("business")
            if not text:
                return {"final": "need_stack"}
            found = resolver.resolve(text)
            if found.outcome == "NONE":
                return {"final": "stack_not_found"}
            if found.outcome == "CARD":
                return {"card": card_stack_sites(list(found.sites))}
            site, numbers = found.sites[0], found.numbers
            if found.by_code:
                notes.append(
                    f"같은 이름의 사업장이 여럿이라 굴뚝 {stack.get('code') or ''}번이 있는 "
                    f"{site.business}({site.region} {site.sigungu})로 정했습니다. "
                    "다르면 알려 주세요."
                )
        infos = _stacks_of_site(data, site.site_id)
        # 굴뚝 번호는 사업장이 정해진 뒤에 읽는다. 명시한 번호가 없으면 단독 숫자 하나가
        # 그 사업장의 실제 굴뚝 번호일 때만 쓴다.
        code = stack.get("code") or (
            numbers[0] if len(numbers) == 1 and numbers[0] in site.codes else None
        )
        keep = {"site_id": site.site_id}
        if code:
            match = [s for s in infos if s.code == str(code)]
            if match:
                return {
                    "command": apply_edit(
                        command, {"stack": {**keep, "stack_key": match[0].stack_key}}
                    )
                }
            alternatives = (
                resolver.similar_with_code(stack.get("business") or "", str(code), site.site_id)
                if stack.get("business")
                else []
            )
            if (
                alternatives
            ):  # 이름이 비슷하고 그 번호가 있는 사업장을 알려 준다(대신 정하지 않는다)
                return {
                    "card": card_stack_sites(
                        alternatives,
                        message=(
                            f"{site.business}에는 굴뚝 {code}번이 없습니다. 이름이 비슷하고 "
                            f"{code}번 굴뚝이 있는 사업장입니다. 맞는 곳을 골라 주세요."
                        ),
                    )
                }
            return {
                "card": card_stack_code(
                    infos, message="그 번호의 굴뚝이 없습니다. 굴뚝 번호를 골라 주세요."
                )
            }
        if len(infos) == 1:
            return {
                "command": apply_edit(command, {"stack": {**keep, "stack_key": infos[0].stack_key}})
            }
        return {"card": card_stack_code(infos)}

    def retype_again(state: State, command: Command, tries: int) -> dict:
        """사업장 이름을 다시 받는다. 두 번 다시 입력해도 안 되면 지도 선택을 안내한다."""
        if tries >= MAX_RETYPES:
            return {"final": "map_hint", "pending": None}
        rest = {k: v for k, v in command.items() if k != "stack"}
        return {
            "final": "retype",
            "pending": {"command": rest, "at": state["now"], "tries": tries},
        }

    def judge(state: State) -> dict:
        command: Command = state["command"]
        intent = command.get("intent") or "aggregate"
        if state.get("cards_asked", 0) >= MAX_CARDS:
            return {"final": "too_many_cards"}
        if intent == "freshness":
            return {"card": None}
        if intent in ("aggregate", "gap"):
            stack = dict(command.get("stack") or {})
            if not stack.get("stack_key"):
                notes: list[str] = []
                outcome = resolve_stack(command, stack, notes)
                if outcome.get("final") == "stack_not_found" and state.get("retry", 0) > 0:
                    return retype_again(state, command, state["retry"] + 1)
                if "final" in outcome or "card" in outcome:
                    return outcome
                command = outcome["command"]
                if notes:
                    update = judge_rest(state, command, intent)
                    update["notices"] = [*(state.get("notices") or []), *notes]
                    return update
        return judge_rest(state, command, intent)

    def judge_rest(state: State, command: Command, intent: str) -> dict:
        pollutants = command.get("pollutants") or []
        if intent == "rank" and len(pollutants) != 1:
            return {"command": command, "card": card_pollutant(single=True)}
        if not pollutants:
            return {"command": command, "card": card_pollutant()}
        if not command.get("time"):
            if _UNSUPPORTED_PERIOD.search(state["message"]):
                return {"command": command, "card": card_period(state["message"])}
            return {"command": command, "card": card_time()}
        try:
            resolve_period(command["time"], _parse_now(state))
        except UnsupportedPeriod:
            return {
                "command": command,
                "card": card_period(state["message"]),
            }  # 거절하지 않고 묻는다
        if intent == "aggregate" and not command.get("operation"):
            return {"command": command, "card": card_operation(state["message"])}
        return {"command": command, "card": None}

    def ask(state: State) -> dict:
        card = state["card"]
        answer = interrupt({"card": public_card(card)})
        option = next((o for o in card["options"] if o["id"] == answer["option_id"]), None)
        asked = state.get("cards_asked", 0) + 1
        if option is None:
            return {"cards_asked": asked}
        if option["skip_part"]:
            return {"skipped": True, "card": None, "cards_asked": asked}
        if option["id"] == "none":
            return {
                **retype_again(state, state["command"], state.get("retry", 0) + 1),
                "card": None,
                "cards_asked": asked,
            }
        return {
            "command": apply_edit(state["command"], option["edit"]),
            "card": None,
            "cards_asked": asked,
        }

    def run(state: State) -> dict:
        command: Command = state["command"]
        intent = command.get("intent") or "aggregate"
        now = _parse_now(state)
        as_of = data.as_of()
        as_of_text = as_of.isoformat() if as_of else None
        if intent == "freshness":
            part = run_freshness(data, now)
            return {
                "parts": [part.model_dump()],
                "data_as_of": as_of_text,
                "route": "DATA",
                "reason": "DONE",
            }
        period = resolve_period(command["time"], now)
        handler = {"aggregate": run_aggregate, "rank": run_rank, "gap": run_gap}[intent]
        part, failed = handler(data, command, period, as_of)
        return {
            "parts": [part.model_dump()],
            "data_as_of": as_of_text,
            # 도구를 실행했으면 값이 비어도 조건은 이어받는다(다음 후속 질문용). 검증 실패는 제외.
            "last_command": None if failed else {"command": command, "delivered_at": state["now"]},
            "route": "DATA",
            "reason": "VERIFY_FAILED" if failed else "DONE",
        }

    def compose(state: State) -> dict:
        notices = list(state.get("notices") or [])
        parts = list(state.get("parts") or [])
        final = state.get("final")
        if state.get("skipped"):
            parts.append(
                Part(
                    part_id="p1",
                    agent="data",
                    status="SKIPPED",
                    label="현황",
                    notice="사용자가 이 부분을 빼고 진행하도록 했습니다.",
                ).model_dump()
            )
        messages = {
            "blocked": BLOCKED_MESSAGE,
            "too_long": TOO_LONG_MESSAGE,
            "scope": (
                "이 질문은 아직 지원하지 않습니다. 굴뚝 측정값 질문"
                "(집계, 전국 순위, 데이터 기준 시각, 데이터가 비는 이유)만 답할 수 있습니다."
            ),
            "need_stack": "어느 굴뚝인지 사업장 이름과 굴뚝 번호를 함께 말씀해 주세요.",
            "stack_not_found": (
                "등록되지 않은 사업장·굴뚝입니다. "
                "사업장 이름과 굴뚝 번호를 확인해 다시 입력해 주세요."
            ),
            "retype": (
                "사업장 이름을 다시 말씀해 주세요. 앞서 말씀하신 조건은 그대로 이어서 조회합니다."
            ),
            "map_hint": "이름으로 찾지 못했습니다. 지도에서 굴뚝을 선택한 뒤 다시 질문해 주세요.",
            "too_many_cards": "확인할 조건이 너무 많습니다. 질문을 다시 입력해 주세요.",
        }
        if final == "compound_unsupported":
            detail = notices[0] if notices else ""
            notices = [
                "한 번에 여러 가지를 묻는 질문으로 보여 일부만 답하지 않고 멈췄습니다"
                + (f" ({detail})" if detail else "")
                + ". 하나씩 나눠서 질문해 주세요."
            ]
        elif final == "compound_failed" and not notices:
            notices.append("질문을 나누지 못했습니다. 하나씩 나눠서 질문해 주세요.")
        elif final == "compound_done" and any(p["status"] != "DONE" for p in parts):
            notices.append("일부 부분은 처리하지 못했습니다. 부분마다 상태를 확인해 주세요.")
        if final in messages:
            notices.append(messages[final])
        return {"parts": parts, "notices": notices}

    def _last_summary(command: dict) -> str:
        """계획기에 보여 줄 직전 조회 한 줄(사람이 읽는 말)."""
        stack = command.get("stack") or {}
        info = data.get_stack(stack.get("stack_key") or "")
        site = site_by_id.get(stack.get("site_id") or "")
        if info is not None:
            where = f"{info.business} 굴뚝 {info.code}번"
        elif site is not None:
            where = f"{site.business} 굴뚝 {stack.get('code') or '?'}번"
        else:
            where = stack.get("business") or "없음"
        return (
            f"굴뚝={where}, 물질={'·'.join(command.get('pollutants') or []) or '없음'}, "
            f"기간={_time_text(command.get('time'))}, 집계={command.get('operation') or '없음'}, "
            f"유형={command.get('intent') or 'aggregate'}"
        )

    def _law_stack(message: str) -> dict | None:
        """법령 질문 속 사업장이 하나로 확실할 때만 굴뚝 정보를 준다(아니면 일반 규정만)."""
        named = resolver.named_sites(message)  # 이름 전체가 질문에 들어 있는 사업장
        if named:
            sites = named
        else:
            found = resolver.resolve(message)
            sites = list(found.sites) if found.outcome == "AUTO" else []
        if len(sites) != 1:  # 같은 이름이 여럿이면 고를 수 없어 일반 규정만 안내한다
            return None
        site = sites[0]
        return {
            "business": site.business,
            "site_id": site.site_id,
            "code": stack_code_from(message, site),
        }

    def route(state: State) -> dict:
        """단일/복합 판별. 복합 단서가 하나라도 있으면 단일 흐름으로 보내지 않는다."""
        reasons = complex_reasons(state["message"])
        clean_shortcut = not other_reasons(
            state["message"]
        )  # 전용 경로는 다른 요청이 섞이지 않았을 때만
        if clean_shortcut and report_only(
            state["message"]
        ):  # 전국 일일 요약은 요약 에이전트 하나로 처리한다
            found = extractor.extract(state["message"], _parse_now(state), has_last=False)
            summary = PlanPart(
                id="p1", agent="report", intent="report", time=found.get("time"), note="일일 요약"
            )
            return {"route": "COMPOUND", "reason": "REPORT", "plan": [asdict(summary)]}
        if (
            clean_shortcut
            and law_only(state["message"])
            and not _LAW_MIXED.search(fold(state["message"]))
        ):  # 법령·제도 질문은 근거 에이전트 하나로 처리한다(예측·리포트가 섞이면 계획기로 보낸다)
            now = _parse_now(state)
            last = state.get("last_command")
            alive = _focus_alive(last, now)
            law = PlanPart(
                id="p1",
                agent="evidence",
                intent="law",
                note="",
                # 질문에 굴뚝이 짚여 있으면 그 굴뚝의 기준·최근값을 법령과 함께 보여 준다
                stack=_law_stack(state["message"]),
                follows_last=alive and bool(_LAW_FOLLOW.match(state["message"])),
            )
            filled = fill_from_last([law], last["command"] if alive and last else None, data)
            out: dict[str, Any] = {"route": "COMPOUND", "reason": "LAW", "plan": [asdict(law)]}
            if filled:
                out["notices"] = [f"직전 조회에서 이어받은 조건: {', '.join(filled)}"]
            return out
        cleaned = resolver.clean_mention(state["message"])
        if not reasons and cleaned and is_group_like(cleaned, resolver):
            return _region_plan(state, cleaned)
        if not reasons and asks_all_stacks(
            state["message"]
        ):  # "굴뚝 전부"는 굴뚝별 값을 나란히 보여 준다
            plan = _all_stacks_plan(state, resolver.clean_mention(state["message"]))
            if plan is not None:
                return plan
        if not reasons and planner is not None:
            extra = unexplained_words(state["message"], resolver)
            if extra:  # 아는 말로 설명되지 않는 낱말이 남으면 단일로 믿지 않고 계획기에게 맡긴다
                reasons = [f"해석되지 않은 말: {', '.join(extra[:3])}"]
        if (
            not reasons
            and planner is not None
            and _focus_alive(state.get("last_command"), _parse_now(state))
        ):
            # 직전 조회가 있는데 규칙이 후속 질문으로 읽지 못하면 거절하지 않고 계획기에게 맡긴다
            found = extractor.extract(state["message"], _parse_now(state), has_last=True)
            if found.get("intent") not in INTENTS:
                reasons = ["직전 조회와의 관계를 규칙으로 읽지 못함"]
        if not reasons:
            return {}
        base = {"route": "COMPOUND", "reason": " / ".join(reasons)[:120]}
        if planner is None:
            return {**base, "final": "compound_unsupported", "notices": [", ".join(reasons)]}
        now = _parse_now(state)
        try:
            last = state.get("last_command")
            alive = _focus_alive(last, now)
            raw = planner.plan(
                state["message"],
                now,
                has_last=alive,
                last=_last_summary(last["command"]) if alive and last else None,
            )
            parts = parse_plan(raw, state["message"])
        except PlanError as error:
            return {**base, "final": "compound_failed", "notices": [str(error)]}
        except Exception:  # noqa: BLE001  계획 호출 실패는 조용히 일부만 답하지 않고 알린다
            return {**base, "final": "compound_failed", "notices": []}
        filled = fill_from_last(parts, last["command"] if alive and last else None, data)
        _inherit_selected(parts, state)
        out: dict[str, Any] = {**base, "reason": "PLAN", "plan": [asdict(p) for p in parts]}
        if filled:
            out["notices"] = [f"직전 조회에서 이어받은 조건: {', '.join(filled)}"]
        return out

    def _region_plan(state: State, cleaned: str) -> dict:
        """지역·업종 묶음 말(충북, 발전소들)은 사업장을 고르지 않고 무엇을 볼지 카드로 묻는다."""
        found = extractor.extract(state["message"], _parse_now(state), has_last=False)
        intent = (
            found.get("intent")
            if found.get("intent") in ("aggregate", "gap", "rank")
            else "aggregate"
        )
        part = PlanPart(
            id="p1",
            agent="data",
            intent=str(intent),
            stack={"business": cleaned},
            pollutants=list(found.get("pollutants") or []),
            time=found.get("time"),
            operation=found.get("operation"),
            metric="ratio" if found.get("metric") == "ratio" else "value",
            note=cleaned,
        )
        return {"route": "COMPOUND", "reason": "REGION", "plan": [asdict(part)]}

    def _all_stacks_plan(state: State, cleaned: str) -> dict | None:
        found = extractor.extract(state["message"], _parse_now(state), has_last=False)
        if resolver.resolve(cleaned).outcome != "AUTO":
            return None
        part = PlanPart(
            id="p1",
            agent="data",
            intent="aggregate",
            stack={"business": cleaned, "code": "all"},
            pollutants=list(found.get("pollutants") or []),
            time=found.get("time"),
            operation=found.get("operation"),
            metric="ratio" if found.get("metric") == "ratio" else "value",
            note=f"{cleaned} 굴뚝 전부",
        )
        return {"route": "COMPOUND", "reason": "ALL_STACKS", "plan": [asdict(part)]}

    def _inherit_selected(parts: list[PlanPart], state: State) -> None:
        """지도에서 고른 굴뚝은 사용자가 직접 정한 것이라 굴뚝 없는 부분에 쓴다."""
        selected = (state.get("context") or {}).get("selectedStackId")
        info = data.get_stack(selected) if selected else None
        for part in parts:
            if info and part.agent == "data" and part.intent in ("aggregate", "gap"):
                if not (part.stack or {}).get("business") and not (part.stack or {}).get("site_id"):
                    part.stack = {"site_id": info.site_id, "code": info.code}

    def compound_judge(state: State) -> dict:
        """사람에게 물어야 할 부분이 남았는지 본다. 모호한 것은 AI가 채우지 않고 카드로 묻는다."""
        parts = [PlanPart(**d) for d in state["plan"]]
        if state.get("cards_asked", 0) >= MAX_CARDS:
            return {"card": None}
        found = next_question(parts, data, resolver, _parse_now(state), state.get("message", ""))
        return {"card": found[1] if found else None}

    def compound_ask(state: State) -> dict:
        card = state["card"]
        answer = interrupt({"card": public_card(card)})
        option = next((o for o in card["options"] if o["id"] == answer["option_id"]), None)
        parts = [PlanPart(**d) for d in state["plan"]]
        if option is not None:
            apply_plan_edit(parts, option["edit"])
        return {
            "plan": [asdict(p) for p in parts],
            "card": None,
            "cards_asked": state.get("cards_asked", 0) + 1,
        }

    def compound_run(state: State) -> dict:
        now = _parse_now(state)
        parts = run_plan(
            [PlanPart(**d) for d in state["plan"]], data, resolver, now, state["message"], evidence
        )
        as_of = data.as_of()
        out: dict[str, Any] = {
            "parts": [p.model_dump() for p in parts],
            "data_as_of": as_of.isoformat() if as_of else None,
            "route": "COMPOUND",
            "reason": "PLAN_DONE",
            "final": "compound_done",
        }
        plan_parts = [PlanPart(**d) for d in state["plan"]]
        if len(plan_parts) == 1 and len(parts) == 1:
            plan, result = plan_parts[0], parts[0]
            if (
                plan.agent == "data"
                and result.status == "DONE"
                and plan.intent in ("aggregate", "gap")
                and plan.stack
            ):
                out["last_command"] = {
                    "command": {
                        "intent": plan.intent,
                        "stack": plan.stack,
                        "pollutants": plan.pollutants,
                        "time": plan.time,
                        "operation": plan.operation,
                        "metric": "value",
                    },
                    "delivered_at": state["now"],
                }
        return out

    def after_guard(state: State) -> str:
        return "compose" if state.get("final") else "route"

    def after_route(state: State) -> str:
        if state.get("final"):
            return "compose"
        return "compound_judge" if state.get("plan") else "understand"

    def after_compound_judge(state: State) -> str:
        return "compound_ask" if state.get("card") else "compound_run"

    def after_understand(state: State) -> str:
        return "compose" if state.get("final") else "judge"

    def after_judge(state: State) -> str:
        if state.get("final"):
            return "compose"
        return "ask" if state.get("card") else "run"

    def after_ask(state: State) -> str:
        return "compose" if state.get("skipped") or state.get("final") else "judge"

    graph = StateGraph(State)
    graph.add_node("guard", guard)
    graph.add_node("route", route)
    graph.add_node("understand", understand)
    graph.add_node("compound_judge", compound_judge)
    graph.add_node("compound_ask", compound_ask)
    graph.add_node("compound_run", compound_run)
    graph.add_node("judge", judge)
    graph.add_node("ask", ask)
    graph.add_node("run", run)
    graph.add_node("compose", compose)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard, ["route", "compose"])
    graph.add_conditional_edges("route", after_route, ["understand", "compound_judge", "compose"])
    graph.add_conditional_edges(
        "compound_judge", after_compound_judge, ["compound_ask", "compound_run"]
    )
    graph.add_edge("compound_ask", "compound_judge")
    graph.add_edge("compound_run", "compose")
    graph.add_conditional_edges("understand", after_understand, ["judge", "compose"])
    graph.add_conditional_edges("judge", after_judge, ["ask", "run", "compose"])
    graph.add_conditional_edges("ask", after_ask, ["judge", "compose"])
    graph.add_edge("run", "compose")
    graph.add_edge("compose", END)
    return graph.compile(checkpointer=checkpointer)


def _stacks_of_site(data: DataSource, site_id: str) -> list[StackInfo]:
    return [s for s in data.list_stacks() if s.site_id == site_id]
