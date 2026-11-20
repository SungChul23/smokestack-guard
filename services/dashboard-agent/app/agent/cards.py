"""색인 카드: 조문마다 미리 만들어 두는 짧은 요약본(도서관 색인 카드).

요약기에 조문 원문을 줄줄이 보내지 않고, 카드로 먼저 찾고 읽는다. 카드는 찾기 위한 보조 자료이며
법적 근거가 아니다. 사용자에게 보이는 근거(출처·발췌)는 항상 조문 원문에서 나온다.

- 카드 파일(corpus/law-evidence-cards.json)은 LLM이 만든 뒤 사람이 검토한다(review_status).
  파일의 카드는 원문 지문(sha256)이 맞고 `verify_card`를 통과할 때만 쓴다.
  없거나 맞지 않는 조문은 결정적 대체 카드(제목 + 첫 문장 + 키워드)로 채운다.
- 이 모듈은 표준 라이브러리만 쓴다(조문 객체는 id·doc_title·article·heading·text 속성만 있으면 된다).
설계: specs/d-analytics/315-doc-summary-answer/
"""

# ruff: noqa: E501  (한글 설명·프롬프트 문장은 폭이 넓어 줄 길이 제한에 걸린다)
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CARD_VERSION = "cards-v1"
MAX_SUMMARY = 200  # 카드 요약 길이 상한(글자)
MAX_KEYWORDS = 14
MAX_QUESTIONS = 5
DEFAULT_CARDS = Path(__file__).parent / "corpus" / "law-evidence-cards.json"

# 문서 용어 → 일상어. 해당 용어가 그 조문 원문에 있을 때만 키워드로 붙인다(원문에 없는 주제를 만들지 않는다).
EVERYDAY_TERMS: dict[str, tuple[str, ...]] = {
    "개선명령": ("초과하면", "넘으면", "고치라는 명령", "시정 명령", "개선하라"),
    "조업정지": ("가동 중지", "운영 중단", "멈추라는 명령", "공장 멈춤"),
    "배출허용기준": ("허용 수치", "기준치", "ppm 기준", "한도", "기준 몇 ppm"),
    "개선계획서": ("계획서 제출", "개선 계획", "무엇을 제출"),
    "측정기기": ("측정기", "자동측정기", "TMS", "측정 장비"),
    "운영기록": ("기록 보관", "기록 보존", "일지"),
    "자가측정": ("직접 측정", "자체 측정", "스스로 측정"),
    "이행": ("이행 보고", "개선 결과 보고", "보고서 제출"),
    "개선기간": ("개선 기한", "언제까지", "기간 얼마"),
    "굴뚝원격감시체계": ("관제센터", "TMS", "원격 감시"),
    "방지시설": ("처리 설비", "집진", "탈황 설비"),
    "과징금": ("벌금", "금전 제재"),
    "배출시설": ("공장 시설", "굴뚝 시설"),
}

_SENTENCE = re.compile(r"[^.①②③④⑤⑥⑦⑧⑨⑩]+(?:[.]|$)")
_ARTICLE_REF = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_ASSERTIVE = re.compile(r"반드시|무조건|확실히|틀림없이|위반입니다|처분을\s*받게")


@dataclass(frozen=True)
class Card:
    id: str
    title: str  # 문서 제목 + 조문 번호(조문 제목)
    summary: str  # 1~2문장
    keywords: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()  # 이 조문이 답하는 대표 질문
    boundary: str = ""  # 이 조문이 다루지 않는 것
    support: tuple[int, ...] = ()  # 요약의 근거 문장 번호(원문 문장 목록의 위치)
    source_len: int = 0
    origin: str = "deterministic"  # llm | deterministic

    def index_text(self) -> str:
        """벡터 색인에 넣는 글: 제목 + 요약 + 키워드 + 대표 질문."""
        return " ".join(
            [self.title, self.summary, " ".join(self.keywords), " ".join(self.questions)]
        )

    def brief(self) -> str:
        """요약기에 보내는 짧은 카드 글."""
        line = f"{self.title}: {self.summary}"
        if self.boundary:
            line += f" (다루지 않음: {self.boundary})"
        return line


def chunk_title(chunk: Any) -> str:
    head = f"{chunk.doc_title} {chunk.article}".strip()
    return head + (f"({chunk.heading})" if getattr(chunk, "heading", "") else "")


def source_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sentences(text: str) -> list[str]:
    """원문을 문장 단위로 나눈다(발췌는 원문의 연속 부분 문자열이어야 한다)."""
    out = [m.group(0).strip() for m in _SENTENCE.finditer(text)]
    return [s for s in out if s]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _heading_words(chunk: Any) -> list[str]:
    words = re.findall(r"[가-힣A-Za-z]{2,}", f"{chunk.heading} {chunk.article}")
    return [w for w in words if w not in ("제조", "조문")]


def deterministic_card(chunk: Any) -> Card:
    """카드 파일이 없을 때의 대체 카드: 제목 + 원문 첫 문장 + 제목 낱말과 일상어 키워드."""
    sents = sentences(chunk.text)
    first = ""
    idx = 0
    for i, s in enumerate(sents):
        if len(s) >= 15:
            first, idx = s, i
            break
    summary = _clip(first or chunk.text.strip(), 150)
    keywords: list[str] = list(dict.fromkeys(_heading_words(chunk)))
    haystack = unicodedata.normalize("NFKC", f"{chunk.heading} {chunk.text}")
    for term, everyday in EVERYDAY_TERMS.items():
        if term in haystack:
            keywords.append(term)
            keywords.extend(everyday)
    keywords = list(dict.fromkeys(keywords))[:MAX_KEYWORDS]
    questions = (f"{chunk.heading}은 무엇인가요" if getattr(chunk, "heading", "") else "",)
    return Card(
        id=chunk.id,
        title=chunk_title(chunk),
        summary=summary,
        keywords=tuple(keywords),
        questions=tuple(q for q in questions if q),
        boundary="",
        support=(idx,),
        source_len=len(chunk.text),
        origin="deterministic",
    )


# ── 검증 ────────────────────────────────────────────────────────────────
def _refs(text: str) -> set[str]:
    return {
        f"{int(m.group(1))}" + (f"-{int(m.group(2))}" if m.group(2) else "")
        for m in _ARTICLE_REF.finditer(text)
    }


def _numbers(text: str) -> set[str]:
    cleaned = _ARTICLE_REF.sub(" ", unicodedata.normalize("NFKC", text))
    cleaned = re.sub(r"[①②③④⑤⑥⑦⑧⑨⑩]", " ", cleaned)
    return {
        n.rstrip("0").rstrip(".") if "." in n else str(int(n)) for n in _NUMBER.findall(cleaned)
    }


def verify_card(card: Card, chunk: Any) -> list[str]:
    """카드의 사실이 원문에 있는지 확인한다. 문제 목록(비어 있으면 통과)."""
    problems: list[str] = []
    if card.id != chunk.id:
        problems.append("카드 id가 조문과 다르다")
    if not card.summary or len(card.summary) > MAX_SUMMARY:
        problems.append("요약 길이가 맞지 않는다")
    if len(card.keywords) > MAX_KEYWORDS or len(card.questions) > MAX_QUESTIONS:
        problems.append("키워드나 대표 질문이 너무 많다")
    allowed = chunk.text + " " + chunk_title(chunk)
    for label, text in (("요약", card.summary), ("경계", card.boundary)):
        for ref in _refs(text) - _refs(allowed):
            problems.append(f"{label}의 조문 번호가 원문에 없다: 제{ref}조")
        for n in _numbers(text) - _numbers(allowed):
            problems.append(f"{label}의 숫자가 원문에 없다: {n}")
        if _ASSERTIVE.search(text):
            problems.append(f"{label}에 단정 표현이 있다")
    for q in card.questions:
        if _refs(q) - _refs(allowed) or _numbers(q) - _numbers(allowed):
            problems.append("대표 질문에 원문에 없는 번호·숫자가 있다")
    sents = sentences(chunk.text)
    if any(i < 0 or i >= len(sents) for i in card.support):
        problems.append("근거 문장 번호가 원문 범위를 벗어났다")
    return problems


# ── 파일 읽기·쓰기 ───────────────────────────────────────────────────────
@dataclass
class CardReport:
    llm: int = 0
    deterministic: int = 0
    rejected: list[str] = field(default_factory=list)  # "id: 사유"


def _card_from_raw(raw: dict[str, Any], chunk: Any) -> Card | None:
    summary = raw.get("summary")
    if not isinstance(summary, str):
        return None
    kw, qs = raw.get("keywords") or [], raw.get("questions") or []
    if not isinstance(kw, list) or not isinstance(qs, list):
        return None
    support = raw.get("support") or []
    boundary = raw.get("boundary")
    return Card(
        id=chunk.id,
        title=chunk_title(chunk),
        summary=summary.strip(),
        keywords=tuple(str(k).strip() for k in kw if str(k).strip())[:MAX_KEYWORDS],
        questions=tuple(str(q).strip() for q in qs if str(q).strip())[:MAX_QUESTIONS],
        boundary=boundary.strip() if isinstance(boundary, str) else "",
        support=tuple(int(i) for i in support if isinstance(i, int)),
        source_len=len(chunk.text),
        origin="llm",
    )


def load_cards(chunks: list[Any], path: Path | None = None) -> tuple[dict[str, Card], CardReport]:
    """조문마다 카드를 정한다: 파일의 카드가 원문 지문·검증을 통과하면 쓰고, 아니면 대체 카드."""
    report = CardReport()
    raw_by_id: dict[str, dict[str, Any]] = {}
    target = path if path is not None else DEFAULT_CARDS
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            raw_by_id = {
                c["id"]: c for c in data.get("cards", []) if isinstance(c, dict) and "id" in c
            }
        except (OSError, ValueError, KeyError, TypeError):
            report.rejected.append("카드 파일: 읽을 수 없어 모두 대체 카드를 쓴다")
    cards: dict[str, Card] = {}
    for chunk in chunks:
        raw = raw_by_id.get(chunk.id)
        card: Card | None = None
        if raw is not None:
            if raw.get("source_sha256") != source_sha(chunk.text):
                report.rejected.append(f"{chunk.id}: 원문이 바뀌어 카드를 쓰지 않는다")
            else:
                card = _card_from_raw(raw, chunk)
                problems = verify_card(card, chunk) if card else ["형식 오류"]
                if problems:
                    report.rejected.append(f"{chunk.id}: {problems[0]}")
                    card = None
        if card is None:
            cards[chunk.id] = deterministic_card(chunk)
            report.deterministic += 1
        else:
            cards[chunk.id] = card
            report.llm += 1
    return cards, report


def cards_fingerprint(cards: dict[str, Card]) -> str:
    """색인이 어떤 카드로 만들어졌는지 가리키는 지문."""
    payload = json.dumps(
        [
            CARD_VERSION,
            [[c.id, c.index_text()] for c in sorted(cards.values(), key=lambda c: c.id)],
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ── LLM 카드 생성 요청(개발: 로컬 Haiku, 운영: 같은 형식으로 클라이언트 주입) ──────────
CARD_SYSTEM = """당신은 법령·공식 안내 문서의 '색인 카드'를 만드는 도서관 사서입니다. make_card 도구로만 답하세요.
굴뚝 NOx·SOx 배출 규제 안내 서비스가 조문을 찾기 위해 쓰는 카드입니다.

## 입력
[조문]: id, 제목, 원문(문장마다 [0], [1] … 번호가 붙어 있다)

## 규칙
- summary: 조문의 핵심을 쉬운 말 1~2문장(150자 이내). 원문에 있는 내용만 쓴다.
  조문 번호·숫자·기간·금액·기관 이름은 원문에 있는 것만 쓴다. 상식으로 보충하지 않는다.
- support: summary의 근거가 된 문장 번호 목록.
- keywords: 이 조문을 찾는 사람이 쓸 낱말 8~12개. 조문 용어와 일상어(예: 초과하면, 넘으면, 기록 보관)를 함께 쓴다.
  단, 이 조문 원문이 다루지 않는 주제의 말은 넣지 않는다.
- questions: 이 조문이 답하는 대표 질문 3~5개(일상 말투, 번호·숫자 없이).
- boundary: 이 조문이 다루지 않는 것을 한 문장(80자 이내)으로. 모르면 빈 문자열.
- 특정 시설의 위반·처분 여부를 단정하지 않는다.
"""

CARD_TOOL = {
    "toolSpec": {
        "name": "make_card",
        "description": "조문 하나의 색인 카드",
        "inputSchema": {
            "json": {
                "type": "object",
                "required": ["summary", "support", "keywords", "questions"],
                "properties": {
                    "summary": {"type": "string"},
                    "support": {"type": "array", "items": {"type": "integer"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "questions": {"type": "array", "items": {"type": "string"}},
                    "boundary": {"type": "string"},
                },
            }
        },
    }
}


def card_user_text(chunk: Any) -> str:
    numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences(chunk.text)))
    return f"[조문]\nid={chunk.id} | {chunk_title(chunk)}\n{numbered}"


def card_request(chunk: Any) -> dict[str, Any]:
    return {
        "system": [{"text": CARD_SYSTEM}],
        "messages": [{"role": "user", "content": [{"text": card_user_text(chunk)}]}],
        "toolConfig": {"tools": [CARD_TOOL], "toolChoice": {"tool": {"name": "make_card"}}},
    }


def cards_file_payload(
    cards: list[dict[str, Any]], corpus_version: str, generated_by: str
) -> dict[str, Any]:
    """카드 파일 형식. review_status가 reviewed로 바뀌기 전에는 '검토 전'이다."""
    return {
        "version": CARD_VERSION,
        "corpus_version": corpus_version,
        "generated_by": generated_by,
        "review_status": "unreviewed",
        "note": "색인용 요약이다. 법적 근거가 아니며 사용자에게 보이는 근거는 조문 원문이다.",
        "cards": cards,
    }
