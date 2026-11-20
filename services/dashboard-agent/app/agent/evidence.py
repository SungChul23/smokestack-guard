"""근거 에이전트: 법령·공식 안내 문서를 조문 단위로 나눠 검색하고, 해당 문장만 발췌해 보여 준다.

원칙
- 문서 전체를 모델에 던지지 않는다. 조문(청크) 단위로 검색해 상위 몇 개만 읽는다.
- 발췌는 청크 원문에서 그대로 잘라 낸 문장이다(원문과 대조해 검증한다). 문장은 지어내지 않는다.
- 이 안내는 특정 시설의 위반·처분을 판정하지 않는다. 자료의 한계(미확보 별표 등)를 항상 붙인다.
- 검색기는 교체 가능하다(`Retriever`). 지금은 글자 조각 키워드 검색이고, 벡터 DB(pgvector 등)를
  붙일 때는 같은 인터페이스로 `VectorRetriever`를 넣고 `HybridRetriever`로 합친다.

자료: `corpus/law-evidence-20261112.json` (확인일 시행본, 대기환경보전법·시행령·시행규칙 조문 14개와
공식 안내 문서 조각 8개). 근거 문서가 늘면 같은 형식의 파일을 추가한다.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.agent.cards import Card, cards_fingerprint, load_cards, sentences
from app.agent.contract import Evidence, Part
from app.agent.stack_facts import StackFacts, facts_text
from app.agent.summarizer import Source, SummaryResult, verify_summary
from app.agent.vindex import (
    DEFAULT_NEURAL_INDEX,
    DEFAULT_TFIDF_INDEX,
    TFIDF_KIND,
    Embedder,
    EmbedderUnavailable,
    FastEmbedEmbedder,
    IndexError_,
    VectorIndex,
    build_tfidf_index,
    load_index,
)

DEFAULT_CORPUS = Path(__file__).parent / "corpus" / "law-evidence-20261112.json"
MAX_EXCERPT = 280
MIN_COVERAGE = 0.2  # 질문 글자 조각(가중)이 청크에 들어 있는 최소 비율. 아래면 근거로 내지 않는다
TOP_K = 3
CANDIDATES = 4  # 요약기에 보내는 조문 후보 수(요약 모드). 후보를 버리는 판단은 요약기와 검증이 한다
RAW_TOP = 2  # 후보 중 원문 일부를 함께 보내는 상위 조문 수(나머지는 카드만)
RAW_LIMIT = 700  # 조문 하나에서 보내는 원문 길이 상한(글자). 검증은 전체 원문으로 한다
RRF_K = 60  # 순위 결합 상수(검색기마다 점수 단위가 달라 점수가 아니라 순위를 합친다)
KEEP_RATIO = 0.55  # 1위 점수의 이 비율 이상만 함께 보인다
HEADING_WEIGHT = 3.0

# 질문에서 근거 검색과 무관한 말(조회 요청·측정 조회 말투)은 뺀다
_NOISE = re.compile(
    r"nox|sox|굴뚝|\d+\s*번|어제|오늘|지금|평균|최댓?값|최대|최소|순위|알려\s*줘|알려|궁금|"
    r"얼마|몇|뭐야|뭔가요|인지|인가요|해줘|줘|좀|그리고|이랑|하고|대한|관한|관련"
)
# 일상 표현 → 문서 표현(의미 검색이 붙기 전의 최소 보조)
_SYNONYMS = {
    "기준": "배출허용기준",
    "넘으면": "초과 개선명령",
    "초과": "초과 개선명령 조업정지",
    "벌금": "과징금 처분",
    "처벌": "조업정지 과징금",
    "공란": "공란 결측 데이터",
    "비어": "공란 결측 데이터",
    "결측": "공란 결측 데이터",
    "측정기": "측정기기 부착",
    "tms": "측정기기 굴뚝원격감시체계",
    "관제센터": "관제센터 굴뚝원격감시체계",
}


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    doc_title: str
    article: str
    heading: str
    text: str
    url: str
    topics: tuple[str, ...] = ()
    kind: str = "law"  # law(법령 조문) | guide(공식 안내)


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    excerpt: str


@dataclass(frozen=True)
class Corpus:
    version: str
    as_of: str
    chunks: tuple[Chunk, ...]
    limitations: tuple[str, ...] = ()
    missing: tuple[str, ...] = field(default_factory=tuple)


def load_corpus(path: Path = DEFAULT_CORPUS) -> Corpus:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    titles = {d["id"]: d.get("title") or d.get("name") or d["id"] for d in data["documents"]}
    supplement = data.get("supplements") or {}
    titles.update({d["id"]: d.get("title") or d["id"] for d in supplement.get("documents", [])})
    chunks = [_chunk(c, titles, "law") for c in data["chunks"]]
    chunks += [_chunk(c, titles, "guide") for c in supplement.get("chunks", [])]
    limits = list(data.get("limitations", [])) + list(supplement.get("limitations", []))
    missing = tuple(m["label"] for m in supplement.get("missing_sources", []))
    return Corpus(data["version"], data["as_of"], tuple(chunks), tuple(limits), missing)


def _chunk(raw: dict, titles: dict[str, str], kind: str) -> Chunk:
    topics = raw.get("topics") or ()
    if isinstance(topics, str):
        topics = tuple(re.findall(r"[A-Za-z_]+", topics))
    return Chunk(
        id=raw["id"],
        doc_id=raw["document_id"],
        doc_title=titles.get(raw["document_id"], raw["document_id"]),
        article=raw.get("article") or "",
        heading=raw.get("heading") or "",
        text=raw["text"],
        url=raw.get("url") or "",
        topics=tuple(topics),
        kind=kind,
    )


def _bigrams(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", text).lower()
    out: list[str] = []
    for word in re.findall(r"[가-힣a-z0-9]+", folded):
        if len(word) == 1:
            out.append(word)
        out += [word[i : i + 2] for i in range(len(word) - 1)]
    return out


def query_terms(query: str) -> list[str]:
    cleaned = _NOISE.sub(" ", unicodedata.normalize("NFKC", query).lower())
    extra = " ".join(add for key, add in _SYNONYMS.items() if key in cleaned)
    return _bigrams(cleaned + " " + extra)


class Retriever(Protocol):
    def search(self, query: str, k: int = TOP_K, *, lenient: bool = False) -> list[Hit]: ...


_PARTICLE = re.compile(
    r"(?:이야|이에요|인가요|인가|이란|이라|으로|에서|에게|에는|이|가|을|를|은|는|의|에|도|로|와|과|만|야)$"
)


_GENERIC = {
    "의무", "이유", "언제", "무엇", "방법", "경우", "때문", "설명", "내용", "어떻게", "얼마나",
    "어떤", "있어", "없어", "해야해", "받으면", "하면", "누가", "어디", "기준", "조치", "조문",
    "근거", "관련",
}  # fmt: skip
_VERBISH = re.compile(
    r"(?:돼|되나|져|해야|하나|있나|없나|받아|받으면|내려|나요|해요|해|예요|이에요|어요|아요|혀|"
    r"있어요|없어요|습니까|할까요|인가요|하죠|돼요|되죠|받나|받죠|하는지|인지|걸려|떨어져|떴는데|했는데)$"
)


def content_words(query: str) -> list[str]:
    """질문에서 근거 검색에 쓸 만한 말(조사를 뗀 두 글자 이상의 낱말)."""
    cleaned = _NOISE.sub(" ", unicodedata.normalize("NFKC", query).lower())
    out: list[str] = []
    for token in re.findall(r"[가-힣a-z0-9]+", cleaned):
        word = _PARTICLE.sub("", token)
        if len(word) >= 2 and word not in _GENERIC and not _VERBISH.search(word):
            out.append(word)
    return out


class KeywordRetriever:
    """글자 조각(bigram) 겹침 + 제목 가중. 벡터 검색 이전의 결정적 검색기."""

    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus
        self._body = [Counter(_bigrams(c.text)) for c in corpus.chunks]
        self._head = [
            Counter(_bigrams(f"{c.heading} {c.article} {c.doc_title}")) for c in corpus.chunks
        ]
        df: Counter[str] = Counter()
        for body, head in zip(self._body, self._head, strict=True):
            df.update(set(body) | set(head))
        n = len(corpus.chunks)
        self._idf = {g: math.log(1 + n / d) for g, d in df.items()}

    def search(self, query: str, k: int = TOP_K, *, lenient: bool = False) -> list[Hit]:
        """lenient=True면 점수가 0보다 크면 상위 k개를 모두 낸다(요약기가 관련 여부를 판단한다)."""
        terms = query_terms(query)
        oov = max(self._idf.values(), default=1.0)  # 문서에 없는 질문 말은 가장 무거운 값으로 센다
        total = sum(self._idf.get(t, oov) for t in terms)
        if not terms or total <= 0:
            return []
        scored: list[tuple[float, int]] = []
        for i in range(len(self.corpus.chunks)):
            got = 0.0
            for t in set(terms):
                w = self._idf.get(t, 0.0)
                if t in self._head[i]:
                    got += w * HEADING_WEIGHT
                elif t in self._body[i]:
                    got += w
            coverage = got / (total * HEADING_WEIGHT) if got else 0.0
            scored.append((coverage, i))
        scored.sort(reverse=True)
        if lenient:
            chunks = self.corpus.chunks
            return [
                Hit(chunks[i], score, _excerpt(chunks[i].text, terms))
                for score, i in scored[:k]
                if score > 0
            ]
        top = scored[0][0] if scored else 0.0
        hits = [
            Hit(self.corpus.chunks[i], score, _excerpt(self.corpus.chunks[i].text, terms))
            for score, i in scored
            if score >= max(MIN_COVERAGE * 0.5, top * KEEP_RATIO) and score >= MIN_COVERAGE * 0.5
        ]
        # 점수가 너무 낮으면 근거로 내지 않는다(아는 척 방지)
        if not hits or hits[0].score < MIN_COVERAGE * 0.5:
            return []
        return hits[:k]


class VectorRetriever:
    """카드 벡터 색인으로 찾는다. embedder가 있으면 신경망 벡터, 없으면 글자 조각 TF-IDF 벡터다."""

    def __init__(
        self, corpus: Corpus, index: VectorIndex, embedder: Embedder | None = None
    ) -> None:
        self.corpus = corpus
        self.index = index
        self.embedder = embedder
        self.name = index.kind
        self._by_id = {c.id: c for c in corpus.chunks}

    def search(self, query: str, k: int = TOP_K, *, lenient: bool = False) -> list[Hit]:
        if self.index.kind == TFIDF_KIND:
            vector: object = self.index.query_vector(query)
        else:
            if self.embedder is None:
                raise EmbedderUnavailable("질문 임베딩기가 없다")
            raw = self.embedder.embed_query(query)
            norm = sum(x * x for x in raw) ** 0.5 or 1.0  # 코사인이 되도록 정규화한다
            vector = [x / norm for x in raw]
        terms = query_terms(query)
        floor = 0.0 if lenient else (0.12 if self.index.kind == TFIDF_KIND else 0.45)
        hits = [
            Hit(self._by_id[i], score, _excerpt(self._by_id[i].text, terms))
            for i, score in self.index.scores(vector)  # type: ignore[arg-type]
            if score > floor and i in self._by_id
        ]
        return hits[:k]


_ARTICLE_NO = re.compile(r"제\s*(\d+)\s*조")


class HybridRetriever:
    """키워드·벡터 검색기들의 순위를 합친다(RRF). '제33조'처럼 조문을 가리키면 그 조문이 먼저다.

    요약 모드(lenient=True)에서만 합친다. 원문 발췌 모드는 기존 키워드 검색을 그대로 쓴다.
    벡터 검색이 중간에 실패하면 그 검색기만 빼고 계속하고, 사실을 `degraded`에 남긴다.
    """

    def __init__(self, keyword: Retriever, others: list[Retriever], corpus: Corpus) -> None:
        self.keyword = keyword
        self.others = others
        self.corpus = corpus
        self.degraded: list[str] = []

    def search(self, query: str, k: int = TOP_K, *, lenient: bool = False) -> list[Hit]:
        if not lenient:
            return self.keyword.search(query, k, lenient=False)
        self.degraded = []
        n = len(self.corpus.chunks)
        scores: dict[str, float] = {}
        hit_by_id: dict[str, Hit] = {}
        for retriever in [self.keyword, *self.others]:
            try:
                ranked = retriever.search(query, n, lenient=True)
            except (EmbedderUnavailable, IndexError_) as error:
                self.degraded.append(
                    f"{getattr(retriever, 'name', type(retriever).__name__)}: {error}"
                )
                continue
            for rank, hit in enumerate(ranked, 1):
                scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + 1.0 / (RRF_K + rank)
                hit_by_id.setdefault(hit.chunk.id, hit)
        pinned = [
            c.id
            for c in self.corpus.chunks
            if _article_matches(c.article, _ARTICLE_NO.findall(query))
        ]
        order = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        order = [*[cid for cid in pinned if cid in scores or cid in hit_by_id], *order]
        seen: list[str] = []
        for cid in order:
            if cid not in seen:
                seen.append(cid)
        by_id = {c.id: c for c in self.corpus.chunks}
        terms = query_terms(query)
        out = []
        for cid in seen[:k]:
            hit = hit_by_id.get(cid) or Hit(by_id[cid], 0.0, _excerpt(by_id[cid].text, terms))
            out.append(Hit(hit.chunk, scores.get(cid, 0.0), hit.excerpt))
        return out


def _article_matches(article: str, numbers: list[str]) -> bool:
    found = _ARTICLE_NO.search(article or "")
    return bool(found) and found.group(1) in numbers


def build_retriever(
    corpus: Corpus,
    cards: dict[str, Card],
    *,
    index_path: Path | None = None,
    neural_path: Path | None = None,
    embedder: Embedder | None = None,
) -> tuple[Retriever, list[str]]:
    """키워드 + TF-IDF 색인(+ 쓸 수 있으면 신경망 색인)을 합친 검색기와 상태 메모를 만든다.

    색인 파일이 없거나 카드와 맞지 않으면 TF-IDF 색인을 메모리에서 다시 만든다.
    신경망 색인은 fastembed·모델 캐시·색인 파일이 모두 있을 때만 쓰고, 아니면 쓰지 않는다.
    """
    keyword = KeywordRetriever(corpus)
    notes: list[str] = []
    fingerprint = cards_fingerprint(cards)
    try:
        index = load_index(index_path or DEFAULT_TFIDF_INDEX, fingerprint)
    except IndexError_ as error:
        index = build_tfidf_index(
            {cid: card.index_text() for cid, card in cards.items()}, fingerprint
        )
        notes.append(f"TF-IDF 색인 파일을 쓰지 못해 메모리에서 만들었다({error})")
    others: list[Retriever] = [VectorRetriever(corpus, index)]
    try:
        neural = load_index(neural_path or DEFAULT_NEURAL_INDEX, fingerprint)
        others.append(VectorRetriever(corpus, neural, embedder or FastEmbedEmbedder()))
    except (IndexError_, EmbedderUnavailable) as error:
        notes.append(f"신경망 임베딩 검색은 쓰지 않는다({error})")
    return HybridRetriever(keyword, others, corpus), notes


def raw_window(text: str, query: str, limit: int = RAW_LIMIT) -> str:
    """조문 원문에서 질문과 가장 겹치는 문장들을 길이 상한 안에서 원문 순서대로 모은다."""
    if len(text) <= limit:
        return text
    sents = sentences(text) or [text]
    wanted = set(query_terms(query))
    scored = sorted(
        range(len(sents)),
        key=lambda i: (-sum(1 for g in set(_bigrams(sents[i])) if g in wanted), i),
    )
    chosen: list[int] = []
    used = 0
    for i in scored:
        if used + len(sents[i]) + 1 > limit and chosen:
            continue
        chosen.append(i)
        used += len(sents[i]) + 1
        if used >= limit:
            break
    piece = " ".join(sents[i] for i in sorted(chosen))
    return piece if len(piece) <= limit else piece[:limit].rstrip() + "…"


def _excerpt(text: str, terms: list[str]) -> str:
    """청크 원문에서 질문과 가장 겹치는 문장을 그대로 잘라 낸다(원문의 연속 부분 문자열)."""
    spans = [m.span() for m in re.finditer(r"[^.①②③④⑤⑥⑦⑧⑨⑩]+(?:[.]|$)", text)] or [(0, len(text))]
    wanted = set(terms)
    best = max(spans, key=lambda s: sum(1 for g in set(_bigrams(text[s[0] : s[1]])) if g in wanted))
    start, end = best
    piece = text[start:end].strip()
    if len(piece) > MAX_EXCERPT:
        piece = piece[:MAX_EXCERPT].rstrip() + "…"
    return piece


REASON_NOTICE = {
    "no_doc": (
        "보관한 법령·공식 안내 문서에 이 질문에 맞는 규정이 없어 안내할 수 없습니다(자료 부족). "
        "근거를 지어내지 않습니다."
    ),
    "out_of_scope": (
        "굴뚝 NOx·SOx 배출 규제와 관련 없는 질문이라 이 서비스에서는 안내하지 않습니다"
        "(서비스 범위 밖)."
    ),
}
CLARIFY_DEFAULT = (
    "어떤 상황인지 알려 주세요. 예: 초과한 물질(NOx/SOx)과 알고 싶은 것(조치, 제출 서류, 기간)."
)
FALLBACK_LEAD = "요약을 만들지 못해 원문 발췌로 보여 드립니다"


def _without(query: str, drop: tuple[str, ...]) -> str:
    """검색 질문에서 사업장 이름 같은 말을 뺀다(이름 글자가 조문 검색을 흐리지 않게)."""
    out = query
    for word in sorted((d for d in drop if d), key=len, reverse=True):
        out = re.sub(re.escape(word), " ", out, flags=re.IGNORECASE)
    return out


class EvidenceAgent:
    def __init__(
        self,
        corpus: Corpus,
        retriever: Retriever | None = None,
        summarizer: object | None = None,
        cards: dict[str, Card] | None = None,
        retrieval_notes: list[str] | None = None,
    ) -> None:
        self.corpus = corpus
        self.retriever = retriever or KeywordRetriever(corpus)
        self.summarizer = summarizer  # 있으면 요약 모드, 없으면 원문 발췌 모드
        self.cards = cards  # 있으면 요약기에 카드 + 원문 일부만 보낸다(없으면 원문 전체 900자)
        self.retrieval_notes = retrieval_notes or []

    def _sources(self, query: str, hits: list[Hit]) -> list[Source]:
        out: list[Source] = []
        for rank, h in enumerate(hits):
            c = h.chunk
            card = self.cards.get(c.id) if self.cards else None
            if card is None:
                out.append(Source(c.id, c.doc_title, c.text, c.article))
                continue
            shown = raw_window(c.text, query, RAW_LIMIT) if rank < RAW_TOP else ""
            out.append(Source(c.id, c.doc_title, shown, c.article, card.brief(), c.text))
        return out

    def _degraded_note(self) -> str:
        degraded = getattr(self.retriever, "degraded", [])
        if not degraded:
            return ""
        return "일부 검색을 쓰지 못해 키워드 중심으로 찾았습니다: " + "; ".join(degraded)

    def _with_note(self, part: Part) -> Part:
        note = self._degraded_note()
        if not note:
            return part
        merged = " ".join(x for x in (part.notice, note) if x)
        return part.model_copy(update={"notice": merged})

    def _unknown(self, query: str) -> list[str]:
        """질문의 낱말 중 보관한 문서 어디에도 나오지 않는 것."""
        text = unicodedata.normalize(
            "NFKC", " ".join(c.text + c.heading for c in self.corpus.chunks)
        )
        return [w for w in dict.fromkeys(content_words(query)) if w not in text.lower()]

    def answer(
        self,
        query: str,
        part_id: str = "p1",
        *,
        facts: StackFacts | None = None,
        drop: tuple[str, ...] = (),
    ) -> Part:
        """질문에 답한다. 요약기가 있으면 요약(+코드 검증), 없거나 실패하면 원문 발췌."""
        block = facts_text(facts) if facts else ""
        if self.summarizer is None:
            return self._answer_extractive(query, part_id, facts_block=block)
        hits = self.retriever.search(_without(query, drop), k=CANDIDATES, lenient=True)
        sources = self._sources(query, hits)
        result = self.summarizer.summarize(query, sources, block)  # type: ignore[attr-defined]
        if result is None:
            return self._answer_extractive(
                query, part_id, lead=f"{FALLBACK_LEAD}(요약 호출 실패)", facts_block=block
            )
        problems = verify_summary(result, sources, block)
        if problems:
            return self._answer_extractive(
                query,
                part_id,
                lead=f"{FALLBACK_LEAD}(요약 검증 실패: {problems[0]})",
                facts_block=block,
            )
        if not result.answerable:
            return self._with_note(self._not_answerable(result, part_id))
        return self._with_note(self._summary_part(result, hits, part_id, block))

    def _not_answerable(self, result: SummaryResult, part_id: str) -> Part:
        if result.reason == "need_clarification":
            clarify = result.clarify
            one_sentence = len(re.findall(r"[?？.!]", clarify)) <= 1
            question = clarify if clarify and one_sentence and not re.search(r"\d", clarify) else ""
            return Part(
                part_id=part_id,
                agent="evidence",
                status="NEEDS_INPUT",
                label="규정",
                notice=question or CLARIFY_DEFAULT,
            )
        return Part(
            part_id=part_id,
            agent="evidence",
            status="UNAVAILABLE",
            label="규정",
            notice=REASON_NOTICE.get(result.reason or "no_doc", REASON_NOTICE["no_doc"]),
        )

    def _summary_part(
        self, result: SummaryResult, hits: list[Hit], part_id: str, block: str
    ) -> Part:
        by_id = {h.chunk.id: h for h in hits}
        lines = [f"법령 요약 (시행본 확인일 {self.corpus.as_of}):"]
        cited: list[Hit] = []
        for n, line in enumerate(result.lines, 1):
            refs = []
            for cid in line.chunk_ids:
                hit = by_id[cid]
                if hit not in cited:
                    cited.append(hit)
                refs.append(f"{hit.chunk.doc_title} {hit.chunk.article}".strip())
            lines.append(f"{n}. {line.text} [{', '.join(dict.fromkeys(refs))}]")
        if block:
            lines.append("")
            lines.append(block)
        lines.append(
            "이 안내는 조문을 요약해 보여 줄 뿐, 특정 시설의 위반·처분 여부를 판단하지 않습니다."
        )
        terms = query_terms(" ".join(line.text for line in result.lines))
        evidence = [
            Evidence(
                source=h.chunk.doc_title,
                article=h.chunk.article,
                effective_date=self.corpus.as_of,
                chunk_id=h.chunk.id,
                url=h.chunk.url or None,
                excerpt=_excerpt(h.chunk.text, terms),
            )
            for h in cited
        ]
        notice_parts = [*result.caveats, *self.corpus.limitations[:2]]
        return Part(
            part_id=part_id,
            agent="evidence",
            status="DONE",
            label="규정",
            answer="\n".join(lines),
            evidence=evidence,
            notice=" ".join(notice_parts) or None,
        )

    def _answer_extractive(
        self, query: str, part_id: str = "p1", *, lead: str = "", facts_block: str = ""
    ) -> Part:
        words = content_words(query)
        unknown = self._unknown(query)
        hits = self.retriever.search(query)
        if words and len(unknown) / len(words) >= 0.5:
            hits = []  # 질문의 핵심어 대부분이 문서에 없다: 비슷한 조문을 억지로 내지 않는다
        if not hits:
            return Part(
                part_id=part_id,
                agent="evidence",
                status="UNAVAILABLE",
                label="규정",
                notice=" ".join(
                    x
                    for x in (
                        lead,
                        "보관한 법령·공식 안내 문서에서 관련 조문 후보를 찾지 못했습니다. "
                        "근거를 지어내지 않습니다.",
                    )
                    if x
                ),
            )
        lines = [f"관련 조문 후보 (시행본 확인일 {self.corpus.as_of}):"]
        if unknown:
            lines.insert(
                0,
                f"질문의 '{', '.join(unknown)}'에 해당하는 말은 보관한 문서에서 찾지 못했습니다. "
                "아래는 일부 낱말이 겹치는 조문 후보입니다.",
            )
        evidence: list[Evidence] = []
        for n, hit in enumerate(hits, 1):
            c = hit.chunk
            head = f"{c.doc_title} {c.article}" + (f"({c.heading})" if c.heading else "")
            lines.append(f"{n}. {head} — “{hit.excerpt}”")
            if c.url:
                lines.append(f"   출처: {c.url}")
            evidence.append(
                Evidence(
                    source=c.doc_title,
                    article=c.article,
                    effective_date=self.corpus.as_of,
                    chunk_id=c.id,
                    url=c.url or None,
                    excerpt=hit.excerpt,
                )
            )
        if facts_block:
            lines.append("")
            lines.append(facts_block)
        lines.append(
            "이 안내는 조문 후보를 보여 줄 뿐, 특정 시설의 위반·처분 여부를 판단하지 않습니다."
        )
        notice = " ".join(x for x in (lead, *self.corpus.limitations[:2]) if x)
        return Part(
            part_id=part_id,
            agent="evidence",
            status="DONE",
            label="규정",
            answer="\n".join(lines),
            evidence=evidence,
            notice=notice or None,
        )


_default: EvidenceAgent | None = None


def default_agent(summarizer: object | None = None) -> EvidenceAgent | None:
    """패키지에 들어 있는 자료로 근거 에이전트를 만든다. 자료가 없으면 None.

    요약기를 주면 요약 모드(코드 검증 포함)로 만들고, 없으면 원문 발췌 모드다.
    """
    global _default
    if summarizer is not None and DEFAULT_CORPUS.exists():
        corpus = load_corpus()
        cards, _report = load_cards(list(corpus.chunks))
        retriever, notes = build_retriever(corpus, cards)
        return EvidenceAgent(
            corpus, retriever, summarizer=summarizer, cards=cards, retrieval_notes=notes
        )
    if _default is None and DEFAULT_CORPUS.exists():
        _default = EvidenceAgent(load_corpus())
    return _default
