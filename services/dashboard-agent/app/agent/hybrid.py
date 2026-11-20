"""정규식 해석기와 LLM 해석기를 합친다. 안전한 쪽으로만 합친다(314 D1).

- 유형이나 굴뚝 말을 읽었으면 LLM을 부르지 않는다(비용). 빈 물질·기간·집계는 카드가 묻는다.
- 유형이나 굴뚝 말을 못 읽었으면 **원문 전체**를 LLM에 보낸다(정규식 결과는 넘기지 않는다).
- LLM이 낸 값은 코드가 다시 검증한다. 통과하지 못한 값은 버린다(카드가 대신 묻는다).
- 정규식과 LLM의 값이 서로 다르면 어느 쪽도 고르지 않고 비운다(카드가 묻는다).
- 사업장 선택은 LLM이 하지 않는다. LLM이 말한 이름은 원문에 실제로 있을 때만 쓰고,
  고르는 것은 인식기다.
- LLM 호출이 실패하면 정규식 결과를 그대로 쓴다.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from app.agent.extractor import Extractor
from app.agent.names import canon
from app.agent.slots import INTENTS, KST, REQUIRED

log = logging.getLogger("agent.hybrid")
POLLUTANTS = {"nox", "sox"}
OPERATIONS = {"mean", "max", "min", "sum"}
TIME_KINDS = {"yesterday", "today", "now", "date", "hours"}
VALUE_SLOTS = ("pollutants", "time", "operation", "metric")


def _clean_time(raw: Any) -> dict[str, Any] | None:
    """LLM이 낸 기간을 검증한다. 지원 모양이 아니면 버린다."""
    if not isinstance(raw, dict) or raw.get("kind") not in TIME_KINDS:
        return None
    kind, value = raw["kind"], raw.get("value")
    if kind == "date":
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return None
        try:
            date.fromisoformat(value)
        except ValueError:
            return None
        return {"kind": "date", "value": value}
    if kind == "hours":
        try:
            hours = int(value)
        except (TypeError, ValueError):
            return None
        return {"kind": "hours", "value": hours} if 1 <= hours <= 72 else None
    return {"kind": kind}


clean_time = _clean_time


def _time_key(time: dict[str, Any] | None) -> tuple | None:
    return None if not time else (time.get("kind"), str(time.get("value")))


def _clean_stack(raw: Any, message: str) -> dict[str, Any] | None:
    """LLM이 말한 사업장 이름은 원문에 실제로 있을 때만 쓴다(지어낸 이름은 버린다)."""
    if not isinstance(raw, dict):
        return None
    business = raw.get("business")
    if not isinstance(business, str) or len(canon(business)) < 2:
        return None
    if canon(business) not in canon(message):
        return None
    stack: dict[str, Any] = {"business": business}
    code = str(raw.get("code") or "")
    if re.fullmatch(r"\d{1,3}", code) and code in message:
        stack["code"] = code
    return stack


def validate(raw: dict[str, Any], message: str) -> dict[str, Any]:
    """LLM 해석 결과를 검증해 쓸 수 있는 칸만 남긴다."""
    pollutants = [p for p in raw.get("pollutants") or [] if p in POLLUTANTS]
    operation = raw.get("operation")
    return {
        "intent": raw.get("intent") if raw.get("intent") in INTENTS else "other",
        "stack": _clean_stack(raw.get("stack"), message),
        "pollutants": sorted(set(pollutants)),
        "time": _clean_time(raw.get("time")),
        "operation": operation if operation in OPERATIONS else None,
        "metric": raw.get("metric") if raw.get("metric") in ("value", "ratio") else None,
        "top_n": raw.get("top_n") if isinstance(raw.get("top_n"), int) else None,
        "patch": raw.get("patch") if isinstance(raw.get("patch"), list) else None,
    }


class HybridExtractor:
    def __init__(self, rule: Extractor, llm: Extractor) -> None:
        self._rule, self._llm = rule, llm

    @staticmethod
    def needs_llm(rule: dict[str, Any], *, has_last: bool) -> bool:
        """정규식이 읽지 못한 것이 있을 때만 부른다.

        유형을 모르거나 굴뚝 말을 못 읽었을 때만 부른다. 물질·기간·집계가 비어 있는 것은
        사용자가 말하지 않은 경우가 대부분이라(시험에서 약 80%) 카드가 묻는다.
        """
        intent = rule.get("intent")
        if intent not in INTENTS:
            return True
        if has_last and rule.get("patch") is not None:
            return False  # 후속 질문은 직전 조건을 이어받는다
        return "stack" in REQUIRED.get(intent, ()) and not rule.get("stack")

    def extract(self, message: str, now: datetime, *, has_last: bool) -> dict[str, Any]:
        rule = self._rule.extract(message, now, has_last=has_last)
        if not self.needs_llm(rule, has_last=has_last):
            return rule
        try:
            raw = self._llm.extract(message, now.astimezone(KST), has_last=has_last)
        except Exception:  # noqa: BLE001  호출 실패는 정규식 결과로 안전하게 이어간다
            log.warning("llm extractor failed; using rule result")
            return rule
        return merge(rule, validate(raw, message), has_last=has_last)


def merge(rule: dict[str, Any], llm: dict[str, Any], *, has_last: bool) -> dict[str, Any]:
    out = dict(rule)
    # 유형: 정규식이 모르면 LLM을 따른다. 정규식이 일반 조회(aggregate)로 읽었으면 그대로 둔다
    # (빠진 굴뚝은 카드가 묻는다). 순위·결측·기준시각처럼 정규식이 말투로 잡은 유형이
    # LLM과 다르면 어느 쪽도 고르지 않고 지원하지 않는 질문으로 둔다.
    if rule["intent"] == "other":
        out["intent"] = llm["intent"]
    elif llm["intent"] != rule["intent"] and rule["intent"] != "aggregate":
        out["intent"] = "other"
    if out["intent"] == "other":
        return out
    # 사업장: 정규식이 못 찾았을 때만 LLM이 말한 이름(원문에 있는 것)을 쓴다.
    if not rule.get("stack") and llm["stack"]:
        out["stack"] = llm["stack"]
    # 값 칸: 한쪽만 있으면 그것을, 둘 다 있고 같으면 그대로, 다르면 비워서 카드로 묻는다.
    for name in VALUE_SLOTS:
        mine, theirs = rule.get(name), llm.get(name)
        if name == "metric":
            if not mine:  # 정규식은 "기준 대비"를 말했을 때만 ratio를 낸다(있으면 그대로 둔다)
                out[name] = theirs
            continue
        same = _time_key(mine) == _time_key(theirs) if name == "time" else mine == theirs
        if not mine:
            out[name] = theirs or mine
        elif theirs and not same:
            out[name] = None
    if out.get("top_n") is None:
        out["top_n"] = llm.get("top_n")
    if has_last and rule.get("patch") is None and llm.get("patch"):
        out["patch"] = [p for p in llm["patch"] if p in VALUE_SLOTS]
    return out
