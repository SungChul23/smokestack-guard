"""앞단 단일/복합 판별. 정규식은 '확실한 단일'을 가려 LLM을 건너뛰는 용도다.

복합 질문(집계·기간·굴뚝이 여럿이거나 다른 에이전트·화면 요청이 섞인 질문)을 단일 흐름으로 보내면
일부만 조용히 답하게 된다(시험 결과, 답한 것의 100%). 그래서 단서가 하나라도 있으면 복합으로 본다.
반대로 단서를 놓친 복합은 여기서 잡지 못한다(정규식 단서의 한계). 그 경우는 LLM 분류가 맡는다.
설계: specs/d-analytics/314-front-interpretation-decisions/compound-plan.md
"""

from __future__ import annotations

import re

from app.agent.fold import fold

_OPERATIONS = (
    r"평균",
    r"최댓?값|최대|최고|맥스|\bmax\b",
    r"최솟?값|최소|최저|\bmin\b",
    r"합계|총합|총량",
    r"중앙값|표준편차|분산",
)
_PERIODS = (
    r"어제|어저께|어재|전일|yesterday",
    r"오늘|금일|today",
    r"지금|현재",
    r"지난주|이번\s*주|지난달|이번\s*달|그저께|엊그제|새벽|오전|오후",
    r"\d+\s*시간",
)
_DAY_PART = re.compile(
    r"(어제|어저께|어재|전일|오늘|금일|그저께|엊그제)\s*(?:새벽|오전|오후|아침|저녁|밤)"
)
_DATE = r"\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}월\s*\d{1,2}일|(?<![\d.])\d{1,2}/\d{1,2}(?![\d/])"
_OTHER_AGENT = (
    r"법령|법적|조문|법\s*기준|(?<![가-힣])법(?![가-힣])|법률|과징금|규정|허용\s*기준\s*(?:설명|이|은|가|뭐)"
    r"|예측|전망|예상|앞으로|위험할|지도|그래프|표로|요약|리포트|보고서|조치|의무|이동해|선택해"
)
_SEQUENCE = (
    r"비교|각각|차이|\bvs\b|그리고|말고|아니고|아니\s*아니|그\s*다음|그다음|전날|그\s*앞|전\s*시간"
    r"|어느\s*쪽|같이\s*(?:봐|보여|줘)|함께"
)
_CALC = (
    r"넘은\s*횟수|초과\s*(?:횟수|시간)|몇\s*번\s*넘|증감|올랐|내렸|변화율|가장\s*높았던\s*시각"
    r"|(?:제일|가장)\s*(?:높|낮)았던\s*시각|언제\s*(?:제일|가장)"
    r"|이상치|튀는\s*값|제외하고|빼고\s*계산|반올림|보정"
    r"|(?:최고|최대|최저|최소)\s*시각|몇\s*(?:퍼센트|%)|중에서?\s|제일\s*큰|가장\s*큰"
)
_OUT_OF_SCOPE = r"소송|변호사|재판|고소|날씨|주식(?!회사)|코인|맛집|배달"
_CHAIN = r"그\s*(?:굴뚝|곳|사업장|값|순위)|걔|찾아서|거기|제일\s*높은\s*곳|가장\s*높은\s*곳"
_HARM = (
    r"삭제|지워|조작|무시|프롬프트|개발자\s*모드|시스템\s*(?:메시지|지시)"
    r"|내부\s*(?:규칙|설정)|비밀|api\s*키|조작|변조|위조|우회|내보내|비밀번호|제한이\s*없|잊고"
    r"|바꿔치기|바꿔서\s*(?:판정|보고|써|만들)"
)


def complex_reasons(message: str) -> list[str]:
    """복합으로 볼 근거를 돌려준다. 비어 있으면 '확실한 단일'이다."""
    text = fold(message)
    found: list[str] = []
    if sum(1 for p in _OPERATIONS if re.search(p, text)) >= 2:
        found.append("집계 방식이 둘 이상")
    # "어제 오전"은 기간 하나다(날과 시간대를 함께 말한 것). 둘로 세면 복합으로 보낸다.
    one_period = _DAY_PART.sub(r"\1", text)
    families = sum(1 for p in _PERIODS if re.search(p, one_period))
    spans = set(re.findall(r"(\d+)\s*시간", text))
    if families + len(set(re.findall(_DATE, text))) + max(len(spans) - 1, 0) >= 2:
        found.append("기간이 둘 이상")
    seen = [m.group(0) for m in re.finditer(r"nox|sox", text)]
    if len(seen) != len(set(seen)) and not re.search(r"(nox|sox)\s*\1", text):
        found.append("같은 물질을 두 번 말함")
    if len(set(seen)) >= 2:
        for p in _OPERATIONS[:4]:
            if len(re.findall(p, text)) >= 2 and not re.search(r"(" + p + r")\s*\1", text):
                found.append("물질마다 집계를 따로 말함")
                break
    numbers = {a or b for a, b in re.findall(r"(\d{1,3})\s*번(?!째)|굴뚝\s*(\d{1,3})(?!\d)", text)}
    if len(numbers) >= 2 or re.search(
        r"\d{1,3}\s*(?:,|、|·|및|와|과|랑|하고)\s*\d{1,3}\s*번", text
    ):
        found.append("굴뚝이 둘 이상")
    bare = r"(?<![\d.\-/])\d{1,3}(?![\d.\-/]|\s*(?:곳|개|위|등|시간|일|월|%|퍼센트|군데))"
    if re.search(r"순위|몇\s*등|몇\s*위|랭킹", text) and re.search(
        r"\d+\s*번|굴뚝\s*\d+|" + bare, text
    ):
        found.append("특정 굴뚝의 순위 요청")
    extra = [
        name
        for name, pattern in (
            ("결측", r"결측|누락|공란|비어|이유|원인"),
            ("기준 시각", r"기준\s*시각|기준시각"),
        )
        if re.search(pattern, text)
    ]
    value_asked = any(re.search(p, text) for p in _OPERATIONS)
    ranked = bool(re.search(r"순위|몇\s*등|몇\s*위|랭킹", text))
    if len(extra) + ranked >= 2 or (extra and value_asked):
        found.append("값과 다른 조회(결측·순위·기준 시각)를 함께 요청")
    if re.search(r"기준\s*시각|기준시각|데이터\s*기준", text) and re.search(r"nox|sox", text):
        found.append("값과 기준 시각을 함께 요청")
    if re.search(_OTHER_AGENT, text):
        found.append("다른 기능(근거·예측·화면·요약) 요청")
    if re.search(_SEQUENCE, text):
        found.append("비교·나열·정정")
    if re.search(_CALC, text):
        found.append("값 계산·가공 요청")
    mixed = r"nox|sox|굴뚝|평균|최대|최소|순위|\d+\s*번"
    if re.search(_OUT_OF_SCOPE, text) and re.search(mixed, text):
        found.append("굴뚝 측정과 관계없는 요청 섞임")
    if re.search(_CHAIN, text):
        found.append("앞 결과를 이어받는 말")
    if re.search(_HARM, text):
        found.append("정상 질문 사이에 낀 위험한 요청")
    return found


# 단일 흐름이 알아듣는 말(기간·집계·물질 이름·요청 말투). 이 밖의 낱말이 남으면 단일로 믿지 않는다.
_KNOWN_SPEECH = re.compile(
    r"^(?:엊그제|그저께|그제|어제|어재|어저께|오늘|금일|지금|방금|현재|새벽|오전|오후|아침|하루|동안|"
    r"이번|지난|시간|최고치|최대치|최저치|최대|최소|평균|합계|총량|합산|측정값|"
    r"기준대비율?|대비율|기준치|허용기준|퍼센트|비율|먼지|녹스|엔오엑스|에스오엑스|아황산가스|이산화황|분진|"
    r"염화수소|질소산화물|황산화물|얼마|알려|봐|궁금|싶|부탁|뭐|몇|보여|주세요|줘|해요|해줘|해주|"
    r"나왔|들어와|그냥|진짜|한번|하나만|그러니까|알고|계속|중에|봐야|뽑아|어떻|어때|어떤|어땠|"
    r"확인|값|수치|숫자|좀|열두|어제자|번|필요|급해|빨리|하는데|해서|조회|보려|보고|그게|그거|"
    r"되나|됐|있나|굴뚝|결측|이유|공란|비어|시각|순위|전국|다시|같은|바꿔|바꾸|으로|에서|기준|그전|전날|전일|그날|"
    r"밤|저녁|야간|심야|간밤|지난밤|밤새|날짜|그대로|해봐|주시|전으로|전은|전에|전의|조건|질문|번호|감사|것만|이면|"
    # 순위·기준 시각을 묻는 말(규칙이 읽는다). '높은지·낮은지'(비교 질문)와 '낮춰서'는 통과시키지
    # 않도록 '높은'·'낮은'은 낱말 전체일 때만이다. 범위(사업장·지역)가 있으면 아래
    # unexplained_words가 순위 말을 아는 말로 보지 않는다.
    r"가장|제일|상위|하위|언제|마지막|높은$|낮은$)"
)
# 사업장·굴뚝·지역을 짚은 질문에서는 순위 말을 아는 말로 보지 않는다(범위가 있는 복합일 수 있다).
_RANK_WORDS = re.compile(r"^(?:가장|제일|상위|하위|높은$|낮은$)")
# "왜 비어 있어?"의 "있어"는 결측을 묻는 말의 일부다. 결측 표현과 함께일 때만 아는 말로 본다
# ("굴뚝 몇 개 있어?"의 "있어"는 아니다).
_GAP_PHRASE = re.compile(r"비어|비었|빠져|빠진|비워")
_GAP_TAIL = re.compile(r"^(?:있어|있는데|있는지|있나)")
# 순위를 묻는 말로 인정하려면 줄 세울 대상도 있어야 한다.
# ("가장 낮은 값으로"는 순위가 아니라 집계를 바꾸는 말이다)
_RANK_NOUN = re.compile(r"순위|굴뚝|곳|사업장|상위|하위|몇\s*등|몇\s*위")
_HANGUL_WORD = re.compile(r"[가-힣]{2,}")
_FOREIGN_WORD = re.compile(r"[a-z]{3,}|[぀-ヿ㐀-鿿]+")
_KNOWN_LATIN = {"nox", "sox", "avg", "mean", "max", "min", "sum", "ppm", "tms", "cems"}


# 굴뚝 번호를 짚은 말. "굴뚝 5곳"의 5는 번호가 아니라 개수다(곳·개·위·등이 붙으면 뺀다).
_CODE_MENTION = re.compile(r"\d+\s*번(?!째)|굴뚝\s*\d+(?!\d|\s*(?:곳|개|위|등))|\d+\s*호기")


def _names_a_scope(text: str, resolver) -> bool:  # noqa: ANN001
    """질문이 사업장·굴뚝 번호·지역을 짚었는가. 그러면 순위 말이 있어도 전국 순위 하나가 아니다."""
    if resolver.parse_regions(text) or _CODE_MENTION.search(text):
        return True
    found = resolver.resolve(text)
    exact_like = found.path in ("EXACT", "EXACT_REGION", "COLLISION", "NUMBER_AMBIGUOUS")
    return found.outcome != "NONE" and (exact_like or found.coverage >= 0.5)


def unexplained_words(message: str, resolver) -> list[str]:  # noqa: ANN001
    """사업장 이름도, 단일 흐름이 아는 말도 아닌 낱말. 남으면 질문에 더 묻는 것이 있을 수 있다."""
    from app.agent.names import canon

    folded = fold(message)
    text = resolver.clean_mention(folded)
    known = resolver.known_text
    scoped = _names_a_scope(folded, resolver)
    rank_ok = not scoped and _RANK_NOUN.search(folded) is not None
    gap_phrase = _GAP_PHRASE.search(folded) is not None
    out: list[str] = []
    for word in _HANGUL_WORD.findall(text):
        if canon(word) in known:
            continue
        if gap_phrase and _GAP_TAIL.match(word):  # "왜 비어 있어?"의 "있어"
            continue
        if _KNOWN_SPEECH.match(word) and (rank_ok or not _RANK_WORDS.match(word)):
            continue
        out.append(word)
    for word in _FOREIGN_WORD.findall(text):
        reading = canon(word)  # 한자·가나는 읽을 수 없어 빈 글이 되므로 이름으로 보지 않는다
        if word in _KNOWN_LATIN or (reading and reading in known):
            continue
        out.append(word)
    return out


OWN_REASON = "다른 기능(근거·예측·화면·요약) 요청"


def other_reasons(message: str) -> list[str]:
    """법령·요약 전용 경로가 스스로 설명하는 근거(다른 기능 요청)를 뺀, 남은 복합 근거."""
    return [r for r in complex_reasons(message) if r != OWN_REASON]


def looks_single(message: str) -> bool:
    return not complex_reasons(message)


# 법령 질문의 "최대 1년", "최소 두 번"은 값 조회 신호가 아니다. 값 조회는 물질·집계·기간 말로 본다.
_DATA_SIGNAL = r"nox|sox|평균|최댓?값|순위|\d+\s*번|어제|오늘|지금"
_LAW_ONLY = (
    r"법|규정|의무|조항|조문|시행규칙|시행령|처벌|과징금|개선명령|조업정지|허용기준|기준값|근거|"
    r"측정기기|관제센터|공란|결측|조치|"
    r"과태료|벌칙|부과금|자가측정|운영기록|보관|계획서|며칠|개선\s*기간|개선\s*기한"
)


def law_only(message: str) -> bool:
    """측정값 조회 없이 법령·제도·자료 안내만 묻는 질문인가."""
    text = fold(message)
    return bool(re.search(_LAW_ONLY, text)) and not re.search(_DATA_SIGNAL, text)


_REPORT = r"리포트|요약|브리핑|보고서|일일"
_ALL_STACKS = r"굴뚝\s*(?:전부|전체|다)|(?:전부|전체|모든)\s*굴뚝"


def report_only(message: str) -> bool:
    """특정 굴뚝이 아니라 전국 일일 요약을 묻는 질문인가."""
    text = fold(message)
    return bool(re.search(_REPORT, text)) and not re.search(r"굴뚝|\d+\s*번|nox|sox", text)


def asks_all_stacks(message: str) -> bool:
    return bool(re.search(_ALL_STACKS, fold(message)))
