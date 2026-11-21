"""지역·묶음 질문("충북 NOx 평균")이 왜 하나의 평균으로 답하기 어려운지 근거를 만든다.

'아직 지원하지 않습니다'가 아니라, 실제 자료로 계산한 사실(수신 비율, 허용기준 종류, 굴뚝 간 편차)을
보여 주고, 지금 실제로 볼 수 있는 방법(지역 안 순위, 전국 순위, 사업장 직접 지정)을 권한다.
숫자는 모두 도구가 계산한 값이다. 설명 문장은 코드 템플릿이다.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.agent.names import SiteResolver, canon
from app.agent.slots import POLLUTANT_LABEL, UnsupportedPeriod, resolve_period
from app.agent.tools import DataSource, RegionProfile, region_profile

_GENERIC = re.compile(
    r"사업장|굴뚝|공장|업체|기업|전부|전체|지역|쪽|에서|내|안|곳|들|의|에|랑|이랑"
)
_GROUP_SUFFIX = re.compile(r"(?:소|사|장|곳|굴뚝|업체|기업|공장|발전소|제철소)들$")
RECEIVE_WARN = 0.8  # 정상 수신 비율이 이보다 낮으면 수신 문제를 이유로 든다
SPREAD_WARN = 3.0  # 최대/중앙값이 이보다 크면 편차를 이유로 든다


def is_group_like(business: str, resolver: SiteResolver, code: object = None) -> bool:
    """지역·업종 묶음처럼 사업장 하나가 아닌 말인가.

    굴뚝 번호가 붙으면(동두천 1번) 굴뚝 하나를 가리키므로 묶음이 아니다.
    """
    if code and str(code) != "all":
        return False
    if _GROUP_SUFFIX.search(business):
        return True
    mentions = resolver.parse_regions(business)
    if not mentions:
        return False
    residual = canon(business)
    for mention in mentions:
        residual = residual.replace(canon(mention.text), "")
    return len(_GENERIC.sub("", residual)) < 2


def profile_for(
    business: str,
    pollutants: list[str],
    time: Any,
    data: DataSource,
    resolver: SiteResolver,
    now: datetime,
) -> tuple[RegionProfile, str, str] | None:
    """지역 프로파일과 (물질 이름, 기간 이름). 물질·기간이 정해지지 않았거나 지역이 비면 None."""
    sites = resolver.sites_in_region(business)
    if not sites or not pollutants or not time:
        return None
    try:
        period = resolve_period(time, now)
    except UnsupportedPeriod:
        return None
    item = pollutants[0]
    profile = region_profile(data, {s.site_id for s in sites}, item, period)
    return profile, POLLUTANT_LABEL[item], period.label


def reasons(profile: RegionProfile, item_label: str, period_label: str) -> list[str]:
    out: list[str] = []
    if profile.n_stacks:
        ratio = profile.n_used / profile.slots_total if profile.slots_total else 0
        if ratio < RECEIVE_WARN or profile.n_with_value < profile.n_stacks:
            out.append(
                f"굴뚝 {profile.n_stacks}개 중 {period_label} {item_label} 값이 있는 굴뚝은 "
                f"{profile.n_with_value}개이고, 정상 수신은 {ratio * 100:.0f}%입니다"
                "(나머지는 미수신·점검 등)."
            )
    if profile.limit_kinds >= 2 and profile.limit_min is not None:
        out.append(
            f"굴뚝마다 허용기준이 달라({profile.limit_min:g}~{profile.limit_max:g} ppm, "
            f"{profile.limit_kinds}종) 같은 값도 의미가 다릅니다."
        )
    if profile.median and profile.maximum and profile.maximum / profile.median >= SPREAD_WARN:
        out.append(
            f"굴뚝 간 편차가 커서(최대 {profile.maximum:.0f} ppm, 중앙값 {profile.median:.0f} ppm) "
            "평균은 일부 굴뚝에 끌려갑니다."
        )
    return out


def explanation(business: str, found: tuple[RegionProfile, str, str] | None) -> str:
    head = f"'{business}'은(는) 사업장 하나가 아니라 지역·묶음으로 보입니다."
    if found is None:
        return head + " 지역 전체를 하나의 평균으로 합치면 원하는 값과 다를 수 있습니다."
    profile, item_label, period_label = found
    why = reasons(profile, item_label, period_label)
    if not why:
        return head + " 굴뚝마다 기준과 측정 대상이 달라 하나의 평균으로는 해석하기 어렵습니다."
    numbered = " ".join(f"({i}) {text}" for i, text in enumerate(why, 1))
    return f"{head} 지역 평균을 내면 원하는 값과 다를 수 있습니다. 이유: {numbered}"
