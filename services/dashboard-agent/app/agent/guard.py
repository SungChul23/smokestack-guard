"""입력 가드레일(결정적 규칙). 모델보다 먼저 돌고,
개인정보는 모델·체크포인트·로그에 닿기 전에 가린다.

차단은 확실한 패턴만 한다. 짧은 말이나 흔한 동사를 막으면 정상 질문이 거절되기 때문이다
(11/18 시험에서 규칙이 거절하는 분기가 짧은 말을 오분류했다).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Action = Literal["ALLOW", "BLOCK", "SMALLTALK"]

# 변조 동사 뒤에 이런 말이 오면 "해 달라"는 요청이 아니라 묻는 말·설명하는 말이다.
# (지워진 건가요 / 조작 적발 시 과태료 / 변조 방지 / 삭제 기준 / 덮어쓰기 되는 주기)
_ASKING = (
    r"(?!(?:기|하기)?\s*(?:지[나는면]|진|졌|져|된|됐|되|돼|의혹|적발|방지|사례|흔적|여부|이력|내역"
    r"|탐지|기준|표시|가능|면|시\s*(?:과태료|처벌|벌칙|제재)|처리\s*(?:된|됐|가|는)|를?\s*막"
    r"|하면|하지\s*않|한\s*적|한\s*사례|하는지|했는지|했나|여부|같|의심|이\s*없|없었|됨|이\s*아니|아닌))"
)

# 묻는 말투이고 "해 달라"는 말이 없으면 변조 '요청'이 아니라 질문·설명이다.
# (조작을 구분하는 기준이 법적으로 어떻게 되나요 / 지우는 게 금지된 행위인가요)
_QUESTION = re.compile(
    r"\?|(?:나요|가요|까요|ㄴ지|는지|인지|었나|했나|있나|할까|건가|건지|어때|뭐야|뭔가)\s*[.!]?\s*$"
)
_REQUEST = re.compile(
    r"줘|주세요|주시|주실|달라|해라|해\s*봐|줄래|줄\s*수|할래|하자|놔|둬|해\s*볼래|부탁|바꿔|바꾸"
)
_QUESTION_OK = {"DATA_TAMPERING", "CONFIG_TAMPERING", "FALSIFY"}

_BLOCK: list[tuple[str, re.Pattern[str]]] = [
    (
        "PROMPT_INJECTION",
        re.compile(
            r"(이전|앞|위|기존)\s*의?\s*(지시|명령|프롬프트|규칙).{0,12}(무시|잊어|따르지)"
            r"|ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above)\s+(instructions?|prompts?)"
            r"|시스템\s*프롬프트|system\s*prompt|탈옥|jailbreak"
            r"|(?:지시|명령|규칙|설정|말)(?:은|는|을|를|들|도)?\s*(?:다\s*|모두\s*|전부\s*)?(?:잊어|잊고|잊으)"
            r"|처음부터\s*다시\s*(?:읽|시작)|이전\s*규칙은.{0,12}(?:적용\s*안|무시|필요\s*없)"
            r"|forget\s+(?:your|all|the|previous|everything)|ignore\s+\S{0,12}\s*instructions?"
            r"|you\s+are\s+now\s+(?:a|an)\s+|pretend\s+(?:to\s+be|you)"
            r"|以前的?指令|之前的?指令|忽略|无视|系统提示|システムプロンプト|以前の指示|指示を無視|無視して"
            r"|(너|당신)\s*의?\s*(지시|규칙|설정).{0,8}(공개|알려|출력)",
            re.IGNORECASE,
        ),
    ),
    (
        "SECRET_REQUEST",
        re.compile(
            r"(api\s*key|api\s*키|비밀번호|패스워드|시크릿|secret|access\s*key|비밀\s*키|토큰)"
            r".{0,14}(알려|보여|출력|말해|공개|줘)"
            r"|(?:비번|로그인\s*정보|접속\s*정보|버킷\s*키|키\s*목록).{0,10}(알려|보여|뽑아|줘|출력)",
            re.IGNORECASE,
        ),
    ),
    (
        "DESTRUCTIVE",
        re.compile(
            r"\b(drop|truncate|alter)\s+(table|database)\b|\bdelete\s+from\b|rm\s+-rf|;\s*--"
            r"|['\"]\s*or\s*['\"]?\w*['\"]?\s*=\s*['\"]?\w|\bor\s+1\s*=\s*1|union\s+select"
            r"|%27|--\s*$|\bxp_cmdshell\b"
            r"|\|\s*(?:nc|bash|sh|curl|wget)\b|;\s*(?:ls|cat|curl|wget|env|whoami)\b|`\s*env\s*`|\$\("
            r"|~/\.aws|/etc/passwd|\bdelete\s*(?:해|하)",
            re.IGNORECASE,
        ),
    ),
    (
        "DATA_TAMPERING",
        re.compile(
            # 지우기·덮어쓰기·변조
            r"(데이터|기록|측정값|이력|테이블|로그|원본|파일|버킷|값).{0,12}"
            r"(?:삭제|지워|지우|날려|날리|비워|덮어쓰|덮어써|변조|조작|위조)"
            + _ASKING
            # 숫자·기준에 맞춰 고치기("번호만 32로 바꿔"는 굴뚝 번호를 바꾸는 말이라 제외)
            + r"|(?<!번호)(?<!번호\s)(?<!번호만)(?<!번호만\s)(?<!굴뚝)(?<!굴뚝\s)"
            r"(?<![\d\-./])\d+\s*(?:으로|로)"
            r"\s*(?:고쳐|바꿔|수정|조작)"
            r"|(?:기록|데이터|측정값|이력|값).{0,6}(?:고쳐|수정해)\s*(?:줘|줄|주|놔|서)"
            r"|(?:기록|데이터|측정값|이력|값|초과분?|행).{0,10}0\s*(?:으로|로)\s*(?:채워|바꿔|바꾸|만들|덮어)"
            r"|(?:값|수치|측정치|평균).{0,8}낮춰\s*(?:줘|주세요|줄래|달라)"
            r"|(?:기준|기준치|한도)\s*(?:을|를)?\s*(?:바꿔|올려|낮춰|수정해)\s*(?:줘|주세요)"
            r"|결측\s*(?:을|를)?\s*0\s*(?:으로|이라고|처리)"
            r"|(?:초과|높은\s*값|튄\s*(?:줄|값)|이상한\s*줄|나쁜\s*(?:것|줄|값)|보기\s*나쁜).{0,14}"
            r"(?:지워|지우|빼\s*(?:줘|주세요|달라)|삭제|치워|숨겨)"
            r"|(?:set|change|raise|lower)\s+the\s+\w+\s+limit|(?:delete|remove|erase|falsify|tamper)"
            r"\s+(?:the\s+|all\s+|these\s+)?(?:data|records?|rows?|values?|logs?)"
            r"|mark\s+.{0,40}\s+as\s+no\s+data"
            r"|(?:고쳐|수정해|바꿔).{0,14}기준\s*(?:안|이하|아래|안쪽)"
        ),
    ),
    (
        "CONFIG_TAMPERING",
        re.compile(
            r"(기준치|기준값|허용\s*기준|보정\s*로직|검증\s*로직|임계값|알람\s*기준)"
            r".{0,12}(?:바꿔|낮춰|올려|수정|해제|끄|꺼)"
            + _ASKING
            # 알림·알람을 꺼 달라는 요청
            + r"|(?:알림|알람|경보).{0,10}(?:설정|기능)?\s*(?:꺼|끄|해제|중지|정지)"
            r"\s*(?:줘|주세요|달라|둬|놔|봐|두고|두면)"
            r"|(?:알림|알람|경보)\s*(?:설정\s*)?(?:꺼|끄|해제)\s*(?:줘|주세요|달라|둬|놔)"
        ),
    ),
    (
        "FALSIFY",
        re.compile(
            r"실제보다\s*(?:낮|높)게|초과\s*(?:아닌|안\s*한)\s*(?:것|걸)처럼|안\s*넘은\s*걸로"
            r"|(?:수치|숫자|값).{0,8}(?:조정|깔끔|낮춰|바꿔|맞춰).{0,8}(?:보고서|리포트|제출)"
            r"|(?:보고서|리포트|제출용).{0,24}(?:낮춰|조정|0\.0|바꿔)"
            r"|(?:무조건|항상)\s*정상(?:이라고|으로)\s*(?:적어|써|말해)|기준.{0,4}0으로\s*쳐"
            # 보고서·요약에서 초과·위반을 빼거나 이상 없음으로 쓰게 하는 요청
            r"|(?:보고서|리포트|요약|제출|본문|제목).{0,24}"
            r"(?:초과|위반|경고|이상|오류|기록).{0,8}(?:빼|지우|숨기|감추|넣지\s*마|누락|없애|제외해)"
            r"|(?:초과|위반|경고|이상|오류).{0,8}(?:빼고|숨기고|감추고|없애고).{0,12}(?:보고서|리포트|요약|제출|올려|써)"
            r"|이상\s*없음['\"’”]?\s*(?:으로|이라고)\s*(?:써|적어|표기)|(?:준수율|적합률)\s*100\s*%?\s*(?:로|으로)\s*(?:써|적어|맞춰)"
            r"|말소|없던\s*(?:걸|거|것)로|통째로\s*빼|깔끔하게\s*(?:기록|데이터|측정)"
        ),
    ),
    (
        "SAFETY_OFF",
        re.compile(
            r"(규칙|제한|제약|필터|안전\s*필터|검증\s*로직|안전장치).{0,10}"
            r"(무시|풀어|해제|꺼\s*줘|끄|없애|신경\s*쓰지|안\s*지키)"
            r"|(관리자|개발자|디버그)\s*모드(?!.{0,16}(?:화면|뜻|어디|무슨|무엇|뭐|떠\s*있))"
            r"|제약\s*없는\s*(?:ai|에이아이|모델)|제한\s*없이"
            r"|슈퍼\s*유저|루트\s*권한|\bsudo\b|권한\s*상승|관리자\s*권한(?:으로|을|\s*줘)"
            r"|(?:이전|앞|위)\s*(?:지시|명령).{0,6}취소|(?:지시|명령)\s*취소"
            r"|(?:시스템\s*)?(?:지시|명령)\s*무시",
            re.IGNORECASE,
        ),
    ),
    (
        "INTERNAL_INFO",
        re.compile(
            r"(도구\s*목록|내부\s*(?:규칙|설정|프롬프트|파일)|개발자\s*프롬프트|지시문\s*원문"
            r"|ssm|파라미터\s*값|환경\s*변수|호스트\s*이름|서버\s*(?:이름|주소|ip)|로그\s*저장\s*위치"
            r"|내부\s*ip|엔드포인트|초기\s*지시|첫\s*문장|시스템\s*메시지|설정\s*파일|프롬프트\s*내용"
            r"|내부\s*로직|접속\s*주소|서비스\s*계정|외부\s*서비스|기본\s*설정|연결된.{0,8}(?:주소|목록))"
            r".{0,14}(적어|알려|보여|출력|붙여넣|복사|공개|줘|번역|요약|공유|설명)",
            re.IGNORECASE,
        ),
    ),
]

# 글자 사이에 공백·점을 끼워 넣은 우회("시 스 템 프 롬 프 트")를 위해, 구분자를 뺀 문장에서
# 확실한 문구만 다시 검사한다. 일반 규칙을 그대로 쓰면 이웃 낱말이 붙어 오탐이 늘어난다.
_COMPACT_BLOCK: list[tuple[str, re.Pattern[str]]] = [
    ("PROMPT_INJECTION", re.compile(r"시스템프롬프트|이전지시|지시무시|지시를무시|이전명령무시")),
    ("SECRET_REQUEST", re.compile(r"(?:비밀번호|api키|토큰|패스워드)(?:알려|보여|출력|줘)")),
    (
        "DATA_TAMPERING",
        re.compile(
            r"(?:데이터|측정값|기록|로그)(?:를|을)?(?:삭제|지워|조작|변조|위조)(?:해|하|줘|좀)"
        ),
    ),
]
_SEPARATORS = re.compile(r"(?<=[가-힣])[\s.\-_·ㆍ,]+(?=[가-힣])")

_PII: list[tuple[str, re.Pattern[str]]] = [
    ("[주민번호]", re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")),
    ("[카드번호]", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")),
    ("[전화번호]", re.compile(r"\b0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}\b")),
    ("[이메일]", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
]

_GREETING = re.compile(
    r"^(안녕|하이|헬로|hello|hi|반가워|처음 뵙|좋은\s*(아침|오후|저녁))", re.IGNORECASE
)
_THANKS = re.compile(r"^(고마워|감사|땡큐|thanks|수고)", re.IGNORECASE)
_ASKS_MORE = re.compile(
    r"그럼|그러면|근데|그리고|\?|알려|얼마|언제|어디|뭐|왜|이유|기준|결측|번은|번도"
)
_DATA_WORDS = re.compile(r"nox|sox|굴뚝|평균|최대|최소|순위|어제|오늘|측정|사업장", re.IGNORECASE)

SMALLTALK_REPLIES = {
    "GREETING": "안녕하세요. 굴뚝의 물질별 측정값을 물어보세요. 예: '어제 ○○ 굴뚝 1 NOx 평균'",
    "THANKS": "도움이 되었다니 다행입니다. 더 궁금한 점이 있으면 물어보세요.",
}
BLOCKED_MESSAGE = "이 요청은 처리할 수 없습니다. 굴뚝 측정값과 관련된 질문만 도와드릴 수 있습니다."


@dataclass(frozen=True)
class GuardResult:
    action: Action
    reason: str
    text: str


def mask_pii(text: str) -> str:
    for label, pattern in _PII:
        text = pattern.sub(label, text)
    return text


MAX_QUESTION_CHARS = 1000  # 이보다 긴 질문은 처리하지 않고 줄여 달라고 안내한다
TOO_LONG_MESSAGE = (
    f"질문이 너무 깁니다. {MAX_QUESTION_CHARS:,}자 이하로 줄여서 핵심만 다시 입력해 주세요."
)


def check_input(message: str) -> GuardResult:
    """차단·인사·통과를 정한다. 반환 text는 개인정보를 가린 문장이다."""
    if len(message.strip()) > MAX_QUESTION_CHARS:
        # 길이를 먼저 본다: 긴 입력을 정규식·모델에 넣지 않고, 상태에도 앞부분만 남긴다
        return GuardResult("BLOCK", "TOO_LONG", mask_pii(message.strip()[:80]) + "…")
    text = mask_pii(message)
    asking = bool(_QUESTION.search(text)) and not _REQUEST.search(text)
    for reason, pattern in _BLOCK:
        if pattern.search(text):
            if asking and reason in _QUESTION_OK:
                continue
            return GuardResult("BLOCK", reason, text)
    compact = _SEPARATORS.sub("", text).lower()
    if compact != text.lower():
        for reason, pattern in _COMPACT_BLOCK:
            if pattern.search(compact):
                return GuardResult("BLOCK", reason, text)
    short = text.strip()
    # 인사 뒤에 질문이 이어지면("고마워 그럼 결측 이유도") 인사로 가로채지 않는다
    if len(short) <= 20 and not _DATA_WORDS.search(short) and not _ASKS_MORE.search(short):
        if _GREETING.search(short):
            return GuardResult("SMALLTALK", "GREETING", text)
        if _THANKS.search(short):
            return GuardResult("SMALLTALK", "THANKS", text)
    return GuardResult("ALLOW", "", text)
