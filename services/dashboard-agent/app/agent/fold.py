"""질문 문장을 단서 검사(정규식)용으로 가지런히 한다.

오타("평ㄱ균", "최댓갑", "펴균")와 장식(이모지, 늘임표, 흩어진 자모) 때문에
같은 요청이 정규식에서 다르게 보이는 문제를 줄인다. 의미를 바꾸지 않는 것만 한다:
- 음절 사이에 끼어든 자모를 지운다(평ㄱ균 → 평균). 자모만의 낱말(ㅇㅅ, ㅋㅋ)은 둔다.
- 이모지·장식 기호를 공백으로 바꾼다.
- 같은 글자의 3번 이상 반복을 2번으로 줄인다(ㅠㅠㅠ).
- 핵심 단서 낱말과 자모 한 글자 차이인 긴 낱말을 그 낱말로 고친다(펴균 → 평균).
이 결과는 단서 검사에만 쓴다. 사용자에게 보이거나 이름 찾기에 쓰는 원문은 바꾸지 않는다.
"""

from __future__ import annotations

import re
import unicodedata

_CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONGSEONG = list(" ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")
_JONGSEONG[0] = ""

# 고칠 만한 핵심 낱말: 질문의 뜻을 정하는 단서만 둔다.
VOCAB = (
    "평균",
    "최댓값",
    "최대값",
    "최솟값",
    "최소값",
    "최고치",
    "최저치",
    "합계",
    "어제",
    "어저께",
    "그저께",
    "그제",
    "오늘",
    "지금",
    "방금",
    "최근",
    "지난주",
    "이번주",
    "이번달",
    "초과",
    "예측",
    "법령",
    "조문",
    "리포트",
    "요약",
    "굴뚝",
    "비교",
    "추세",
    "기준",
    "알려줘",
    "보여줘",
    "어디",
)

_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⬀-⯿️‍←-⇿⌀-⏿]")
_STRAY_JAMO = re.compile(r"(?<=[가-힣])[ㄱ-ㅎㅏ-ㅣ]+(?=[가-힣])|(?<=[가-힣])[ㄱ-ㅎㅏ-ㅣ]+(?=\s|$)")
_REPEAT = re.compile(r"(.)\1{2,}")
_NON_JAMO = re.compile(r"[^ㄱ-ㅎㅏ-ㅣ]+")
_HANGUL_RUN = re.compile(r"[가-힣]+")


def _jamo(word: str) -> str:
    out: list[str] = []
    for ch in word:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(_CHOSEONG[code // 588])
            out.append(_JUNGSEONG[(code % 588) // 28])
            out.append(_JONGSEONG[code % 28])
        else:
            out.append(ch)
    return "".join(out)


_VOCAB_JAMO = [(w, _jamo(w)) for w in VOCAB]


def _within_one(a: str, b: str) -> bool:
    """두 자모열이 글자 하나(끼움·빠짐·바뀜)만큼 다른가."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long[i]:
        i += 1
    return short[i:] == long[i + 1 :]


def _repair(run: str) -> str:
    """한글 덩어리 안에서 핵심 낱말과 한 글자 차이인 부분을 그 낱말로 고친다."""
    if run in VOCAB:
        return run
    for word, word_jamo in _VOCAB_JAMO:
        if len(word_jamo) < 6:  # 짧은 낱말은 다른 말(언제↔어제)로 잘못 고치기 쉬워 고치지 않는다
            continue
        n = len(word)
        for size in (n, n - 1, n + 1):
            if size < 2:
                continue
            for start in range(0, len(run) - size + 1):
                piece = run[start : start + size]
                if piece == word:
                    break
                # 첫 글자(자음+모음)는 같아야 한다: "수위"→"순위" 같은 다른 낱말로의 오교정을 줄인다
                if piece[0] != word[0] and _jamo(piece[0])[:2] != _jamo(word[0])[:2]:
                    continue
                if len(_jamo(piece)) >= 5 and _within_one(_jamo(piece), word_jamo):
                    return run[:start] + word + run[start + size :] if run != piece else word
    return run


# 흔한 말줄임·오타. 짧은 낱말이라 자모 거리로는 고치지 않고 표로 둔다.
_ALIASES = (
    (re.compile(r"어젯(?!밤)"), "어제"),
    (re.compile(r"(?<![가-힣])젤(?![가-힣])"), "제일"),
    (re.compile(r"놉[은다]"), "높은"),
)


def fold(message: str) -> str:
    text = _EMOJI.sub(" ", message.lower())
    text = _REPEAT.sub(r"\1\1", text)
    text = _STRAY_JAMO.sub("", text)  # NFKC보다 먼저: NFKC가 호환 자모를 다른 자모로 바꾼다
    # 낱자모는 NFKC가 바꾸지 않도록 그대로 둔다
    text = _NON_JAMO.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), text)
    for pattern, replacement in _ALIASES:
        text = pattern.sub(replacement, text)
    return _HANGUL_RUN.sub(lambda m: _repair(m.group(0)), text)
