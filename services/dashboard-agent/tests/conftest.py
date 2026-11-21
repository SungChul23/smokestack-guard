"""에이전트 시험 공용 자료: 작은 가짜 데이터와 서비스 조립."""

from datetime import datetime, timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.data import InMemoryDataSource
from app.agent.extractor import RuleExtractor
from app.agent.graph import sites_from
from app.agent.names import SiteResolver
from app.agent.service import AgentService
from app.agent.slots import KST
from app.agent.tools import Observation, StackInfo

DAY = datetime(2026, 11, 10, tzinfo=KST)
AS_OF = DAY + timedelta(hours=23, minutes=30)


def slot(i: int) -> datetime:
    return DAY + timedelta(minutes=30 * i)


def make_rows() -> dict:
    """100:1 NOx: 0..47 값. 2,3번 미수신(3), 4번 보수 중(4), 10번 행 없음. 기준 200."""
    nox = []
    for i in range(48):
        if i == 10:
            continue
        if i in (2, 3):
            nox.append(Observation(slot(i), 0.0, 200.0, 3))
        elif i == 4:
            nox.append(Observation(slot(i), 0.0, 200.0, 4))
        else:
            nox.append(Observation(slot(i), float(i), 200.0, 0))
    not_monitored = [Observation(slot(i), 0.0, None, 8) for i in range(48)]
    plain = [Observation(slot(i), 10.0, 100.0, 0) for i in range(48)]
    return {
        ("100:1", "nox"): nox,
        ("100:1", "sox"): not_monitored,
        ("100:2", "nox"): plain,
        ("200:3", "nox"): plain,
        ("301:1", "nox"): plain,
        ("302:1", "nox"): [Observation(slot(i), 20.0, 100.0, 0) for i in range(48)],
    }


def make_data() -> InMemoryDataSource:
    stacks = [
        StackInfo("100:1", "100", "㈜가나에너지", "1", "경기도"),
        StackInfo("100:2", "100", "㈜가나에너지", "2", "경기도"),
        StackInfo("200:3", "200", "다라화학(주)", "3", "울산광역시"),
        StackInfo("301:1", "301", "동서식품(주)", "1", "충청북도"),
        StackInfo("302:1", "302", "동서식품(주)", "1", "인천광역시"),
    ]
    return InMemoryDataSource(stacks, make_rows(), AS_OF)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class CountingExtractor:
    def __init__(self, inner) -> None:
        self.inner, self.calls = inner, 0

    def extract(self, message, now, *, has_last):
        self.calls += 1
        return self.inner.extract(message, now, has_last=has_last)


@pytest.fixture
def clock() -> Clock:
    return Clock(datetime(2026, 11, 11, 9, 0, tzinfo=KST))


@pytest.fixture
def extractor() -> CountingExtractor:
    return CountingExtractor(RuleExtractor(SiteResolver(sites_from(make_data()))))


@pytest.fixture
def service(extractor, clock) -> AgentService:
    return AgentService(extractor, make_data(), InMemorySaver(), clock, "rule-dev")
