"""데이터 원본 구현. 운영은 RDS(`obs.*`)를 읽게 될 자리이고, 지금은 시험·로컬용 두 가지가 있다.

- InMemoryDataSource: 시험용
- JsonDayDataSource: 로컬에 만든 하루치 정적 파일(`data/day/`)을 읽는다(개발 확인용)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.agent.slots import KST, norm_name
from app.agent.tools import (
    NOT_MONITORED,
    OK,
    RAW_STATUS,
    Observation,
    StackInfo,
)

ITEM_INDEX = {"nox": 0, "sox": 1}


class InMemoryDataSource:
    def __init__(
        self,
        stacks: list[StackInfo],
        rows: dict[tuple[str, str], list[Observation]],
        as_of: datetime | None = None,
    ) -> None:
        self._stacks = {s.stack_key: s for s in stacks}
        self._rows = rows
        self._as_of = as_of

    def find_stacks(self, business: str, code: str | None) -> list[StackInfo]:
        key = norm_name(business)
        return [
            s
            for s in self._stacks.values()
            if norm_name(s.business) == key and (code is None or s.code == str(code))
        ]

    def get_stack(self, stack_key: str) -> StackInfo | None:
        return self._stacks.get(stack_key)

    def list_stacks(self) -> list[StackInfo]:
        return list(self._stacks.values())

    def observations(
        self, stack_key: str, item: str, start: datetime, end: datetime
    ) -> list[Observation]:
        return [o for o in self._rows.get((stack_key, item), []) if start <= o.measured_at < end]

    def as_of(self) -> datetime | None:
        return self._as_of


def _sigungu(address: str) -> str:
    """주소의 두 번째 말이 시·군·구이면 소재지로 본다(검수된 값이 아니라 주소에서 뽑은 값)."""
    tokens = address.split()
    return tokens[1] if len(tokens) > 1 and tokens[1][-1] in "시군구" else ""


def parse_cell(value: object, limit: object) -> Observation | None:
    """원문 칸([값, 기준]) → 상태 코드와 숫자. 상태 행의 value는 0, status_code로 구분한다."""
    raw_limit = _number(limit)
    if value is None:
        # 값과 기준이 모두 없으면 그 굴뚝이 측정하지 않는 물질이다.
        code = NOT_MONITORED if limit is None else 99
        return Observation(datetime.min, 0.0, raw_limit, code)
    number = _number(value)
    if number is not None:
        return Observation(datetime.min, number, raw_limit, OK)
    text = str(value).replace(" ", "")
    return Observation(datetime.min, 0.0, raw_limit, RAW_STATUS.get(text, 99))


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


class JsonDayDataSource:
    """`public/data/day/` 형식(latest.js, history-index.json, history/<사업장>/<날짜>.json)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        text = (self.root / "latest.js").read_text(encoding="utf-8")
        start = text.index("{")
        local, _ = json.JSONDecoder().raw_decode(text[start:])
        # 사업장 목록(id, 이름, 지역)은 latest.js에서, 굴뚝 번호와 관측은 이력 파일에서 읽는다.
        self._sites = {
            site["site_id"]: (
                site["source_name"],
                site.get("boundary_region", ""),
                _sigungu(site.get("address", "")),
            )
            for site in local["sites"]
        }
        self._index = json.loads((self.root / "history-index.json").read_text(encoding="utf-8"))
        self._stacks: dict[str, StackInfo] = {}
        for site_id, entries in self._index["sites"].items():
            name, region, sigungu = self._sites.get(site_id, ("", "", ""))
            for entry in entries[:1]:
                chunk = json.loads((self.root / entry["path"]).read_text(encoding="utf-8"))
                for stack in chunk["stacks"]:
                    code = str(stack["stack_code"])
                    key = f"{site_id}:{code}"
                    self._stacks[key] = StackInfo(key, site_id, name, code, region, sigungu)
        self._cache: dict[str, dict[str, list[list]]] = {}

    def find_stacks(self, business: str, code: str | None) -> list[StackInfo]:
        key = norm_name(business)
        return [
            s
            for s in self._stacks.values()
            if norm_name(s.business) == key and (code is None or s.code == str(code))
        ]

    def get_stack(self, stack_key: str) -> StackInfo | None:
        return self._stacks.get(stack_key)

    def list_stacks(self) -> list[StackInfo]:
        return list(self._stacks.values())

    def _site_rows(self, site_id: str) -> dict[str, list[list]]:
        if site_id not in self._cache:
            rows: dict[str, list[list]] = {}
            for entry in self._index["sites"].get(site_id, []):
                chunk = json.loads((self.root / entry["path"]).read_text(encoding="utf-8"))
                for stack in chunk["stacks"]:
                    rows.setdefault(f"{site_id}:{stack['stack_code']}", []).extend(
                        stack["observations"]
                    )
            self._cache[site_id] = rows
        return self._cache[site_id]

    def observations(
        self, stack_key: str, item: str, start: datetime, end: datetime
    ) -> list[Observation]:
        site_id = stack_key.split(":", 1)[0]
        out: list[Observation] = []
        for row in self._site_rows(site_id).get(stack_key, []):
            t = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
            if not start <= t < end:
                continue
            value, limit = row[1][ITEM_INDEX[item]]
            parsed = parse_cell(value, limit)
            if parsed:
                out.append(Observation(t, parsed.value, parsed.limit, parsed.status_code))
        return out

    def as_of(self) -> datetime | None:
        latest = self._index.get("measurement_time_max")
        if not latest:
            return None
        return datetime.strptime(latest, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
