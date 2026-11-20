"""색인 카드·로컬 벡터 색인·결합 검색·요약기 입력 축소. 모델 호출 없이 결정적으로 시험한다."""

import json

import pytest

from app.agent.cards import (
    Card,
    cards_fingerprint,
    deterministic_card,
    load_cards,
    sentences,
    source_sha,
    verify_card,
)
from app.agent.evidence import (
    CANDIDATES,
    RAW_TOP,
    EvidenceAgent,
    HybridRetriever,
    KeywordRetriever,
    VectorRetriever,
    build_retriever,
    load_corpus,
    raw_window,
)
from app.agent.summarizer import (
    GroundedSummarizer,
    Source,
    SummaryLine,
    SummaryResult,
    summary_user_text,
    verify_summary,
)
from app.agent.vindex import (
    EmbedderUnavailable,
    IndexError_,
    build_tfidf_index,
    load_index,
    save_index,
)

CORPUS = load_corpus()
CHUNKS = list(CORPUS.chunks)
BY_ID = {c.id: c for c in CHUNKS}


def all_cards():
    cards, _ = load_cards(CHUNKS, path=None)
    return cards


# ── 카드 ──────────────────────────────────────────────────────────────
def test_deterministic_cards_are_verified_substrings_of_the_source():
    for chunk in CHUNKS:
        card = deterministic_card(chunk)
        assert verify_card(card, chunk) == [], chunk.id
        assert card.summary.rstrip("…") in chunk.text
        assert card.origin == "deterministic" and card.keywords


def test_everyday_words_are_added_only_when_the_source_has_the_term():
    improvement = next(c for c in CHUNKS if c.heading == "개선명령")
    card = deterministic_card(improvement)
    assert "초과하면" in card.keywords
    storage = next(c for c in CHUNKS if "운영기록 보존" in c.heading)
    assert "초과하면" not in deterministic_card(storage).keywords


def test_card_verification_rejects_invented_facts():
    chunk = BY_ID["law-279785-article-33"]
    good = deterministic_card(chunk)
    assert verify_card(good, chunk) == []
    invented_number = Card(**{**good.__dict__, "summary": "30일 안에 개선해야 한다"})
    assert any("숫자" in p for p in verify_card(invented_number, chunk))
    invented_ref = Card(**{**good.__dict__, "summary": "제99조에 따라 처분한다"})
    assert any("조문 번호" in p for p in verify_card(invented_ref, chunk))
    assertive = Card(**{**good.__dict__, "summary": "반드시 조업정지가 된다"})
    assert any("단정" in p for p in verify_card(assertive, chunk))
    bad_support = Card(**{**good.__dict__, "support": (99,)})
    assert any("근거 문장" in p for p in verify_card(bad_support, chunk))


def test_card_file_is_used_only_when_hash_and_verification_pass(tmp_path):
    chunk = BY_ID["law-279785-article-33"]
    other = BY_ID["law-279785-article-34"]
    rows = [
        {  # 정상: 쓴다
            "id": chunk.id, "source_sha256": source_sha(chunk.text),
            "summary": "배출허용기준을 초과하면 개선명령을 할 수 있다.", "support": [0],
            "keywords": ["개선명령", "초과하면"], "questions": ["초과하면 무슨 명령을 받나요"],
            "boundary": "조업정지는 다루지 않는다",
        },
        {  # 원문 지문이 다르다: 쓰지 않는다
            "id": other.id, "source_sha256": "0" * 64, "summary": "x", "support": [0],
            "keywords": [], "questions": [],
        },
    ]  # fmt: skip
    path = tmp_path / "cards.json"
    path.write_text(json.dumps({"cards": rows}, ensure_ascii=False), encoding="utf-8")
    cards, report = load_cards(CHUNKS, path)
    assert cards[chunk.id].origin == "llm" and report.llm == 1
    assert cards[other.id].origin == "deterministic"
    assert any(other.id in line for line in report.rejected)


def test_a_card_that_fails_verification_falls_back_and_a_corrupt_file_is_survivable(tmp_path):
    chunk = BY_ID["law-279785-article-33"]
    bad = {"id": chunk.id, "source_sha256": source_sha(chunk.text), "summary": "30일 이내에 한다",
           "support": [0], "keywords": [], "questions": []}  # fmt: skip
    path = tmp_path / "cards.json"
    path.write_text(json.dumps({"cards": [bad]}), encoding="utf-8")
    cards, report = load_cards(CHUNKS, path)
    assert cards[chunk.id].origin == "deterministic" and report.rejected
    path.write_text("{ not json", encoding="utf-8")
    cards, report = load_cards(CHUNKS, path)
    assert report.deterministic == len(CHUNKS) and report.rejected


def test_card_fingerprint_changes_when_a_card_changes():
    cards = all_cards()
    before = cards_fingerprint(cards)
    changed = dict(cards)
    first = next(iter(changed))
    changed[first] = Card(**{**changed[first].__dict__, "summary": "바뀐 요약"})
    assert cards_fingerprint(changed) != before


# ── 벡터 색인 ─────────────────────────────────────────────────────────
def test_tfidf_index_roundtrip_and_fingerprint_guard(tmp_path):
    cards = all_cards()
    fp = cards_fingerprint(cards)
    index = build_tfidf_index({i: c.index_text() for i, c in cards.items()}, fp)
    path = tmp_path / "index.json"
    save_index(index, path)
    loaded = load_index(path, fp)
    assert loaded.kind == "char-ngram-tfidf-v1" and loaded.ids == index.ids
    query = index.query_vector("초과하면 어떤 조치를 받나요")
    assert (
        index.scores(query)[0][0]
        == loaded.scores(loaded.query_vector("초과하면 어떤 조치를 받나요"))[0][0]
    )
    with pytest.raises(IndexError_):
        load_index(path, "다른 지문")
    with pytest.raises(IndexError_):
        load_index(tmp_path / "없음.json", fp)


def test_vector_retriever_finds_the_improvement_order_for_an_everyday_question():
    cards = all_cards()
    index = build_tfidf_index(
        {i: c.index_text() for i, c in cards.items()}, cards_fingerprint(cards)
    )
    hits = VectorRetriever(CORPUS, index).search("초과하면 어떤 조치를 받나요", 3, lenient=True)
    assert any(h.chunk.heading in ("개선명령", "조업정지명령 등") for h in hits)
    assert all(0.0 <= h.score <= 1.0001 for h in hits)


class BrokenNeural:
    name = "neural-fastembed"

    def search(self, query, k=3, *, lenient=False):
        raise EmbedderUnavailable("모델 캐시가 없다")


def test_hybrid_survives_a_broken_vector_search_and_says_so():
    cards = all_cards()
    index = build_tfidf_index(
        {i: c.index_text() for i, c in cards.items()}, cards_fingerprint(cards)
    )
    hybrid = HybridRetriever(
        KeywordRetriever(CORPUS), [VectorRetriever(CORPUS, index), BrokenNeural()], CORPUS
    )
    hits = hybrid.search("초과하면 어떤 조치를 받나요", 4, lenient=True)
    assert hits and hybrid.degraded and "모델 캐시" in hybrid.degraded[0]


def test_hybrid_puts_an_explicitly_named_article_first():
    cards = all_cards()
    index = build_tfidf_index(
        {i: c.index_text() for i, c in cards.items()}, cards_fingerprint(cards)
    )
    hybrid = HybridRetriever(KeywordRetriever(CORPUS), [VectorRetriever(CORPUS, index)], CORPUS)
    hits = hybrid.search("대기환경보전법 제34조는 뭐라고 되어 있나요", 4, lenient=True)
    assert hits[0].chunk.id == "law-279785-article-34"


def test_build_retriever_rebuilds_in_memory_when_the_index_file_is_stale(tmp_path):
    cards = all_cards()
    stale = tmp_path / "old.json"
    stale.write_text("{}", encoding="utf-8")
    retriever, notes = build_retriever(
        CORPUS, cards, index_path=stale, neural_path=tmp_path / "none.json"
    )
    assert any("메모리에서" in n for n in notes) and any("신경망" in n for n in notes)
    assert retriever.search("개선명령", 3, lenient=True)


# ── 요약기 입력 축소 ───────────────────────────────────────────────────
def test_raw_window_keeps_original_sentences_within_the_limit():
    chunk = max(CHUNKS, key=lambda c: len(c.text))
    window = raw_window(chunk.text, "개선명령 이행 보고", limit=300)
    assert len(window) <= 301
    for piece in sentences(window.rstrip("…")):
        assert piece[:20] in chunk.text
    assert raw_window("짧은 조문입니다.", "아무거나", limit=300) == "짧은 조문입니다."


class FixedSummarizer:
    """요청 글을 기록하고, 정해 둔 결과를 돌려준다."""

    def __init__(self, result):
        self.result, self.questions, self.sources = result, [], []

    def summarize(self, question, sources, facts=""):
        self.questions.append(question)
        self.sources.append(sources)
        return self.result


def test_agent_sends_cards_plus_one_raw_window_and_verifies_against_the_full_text():
    cards = all_cards()
    index = build_tfidf_index(
        {i: c.index_text() for i, c in cards.items()}, cards_fingerprint(cards)
    )
    hybrid = HybridRetriever(KeywordRetriever(CORPUS), [VectorRetriever(CORPUS, index)], CORPUS)
    # 요약기가 낸 문장은 원문 전체(창 밖)에 있는 조문 번호를 말해도 통과한다
    full = BY_ID["law-279785-article-33"]
    result = SummaryResult(
        True, None, [SummaryLine("초과하면 개선명령을 할 수 있습니다.", (full.id,))]
    )
    fake = FixedSummarizer(result)
    agent = EvidenceAgent(CORPUS, hybrid, summarizer=fake, cards=cards)
    part = agent.answer("초과하면 어떤 조치를 받나요")
    assert part.status == "DONE"
    sources = fake.sources[0]
    assert len(sources) <= CANDIDATES
    assert all(s.card for s in sources)  # 카드는 모두
    assert sum(1 for s in sources if s.text) == RAW_TOP  # 원문 일부는 상위 RAW_TOP개만
    assert all(s.full_text for s in sources)  # 검증용 원문 전체는 코드가 갖는다
    text = summary_user_text("질문", sources)
    assert "[후보 카드]" in text and "[핵심 원문]" in text
    legacy = summary_user_text(
        "질문", [Source(s.id, s.title, s.full_text, s.article) for s in sources]
    )
    assert len(text) < len(legacy)


def test_agent_notice_mentions_a_degraded_vector_search():
    cards = all_cards()
    hybrid = HybridRetriever(KeywordRetriever(CORPUS), [BrokenNeural()], CORPUS)
    full = BY_ID["law-279785-article-33"]
    fake = FixedSummarizer(
        SummaryResult(True, None, [SummaryLine("개선명령을 할 수 있습니다.", (full.id,))])
    )
    part = EvidenceAgent(CORPUS, hybrid, summarizer=fake, cards=cards).answer("개선명령이 뭐예요")
    assert part.status == "DONE" and "일부 검색을 쓰지 못해" in (part.notice or "")


def test_verifier_blocks_a_sanction_topic_that_is_not_in_the_sources():
    src = [Source("a", "법", "개선명령을 할 수 있다.", "제33조", "카드", "개선명령을 할 수 있다.")]
    bad = SummaryResult(
        True, None, [SummaryLine("초과하면 허가가 취소될 수 있고 과태료도 있습니다.", ("a",))]
    )
    problems = verify_summary(bad, src)
    assert any("과태료" in p for p in problems)
    in_source = [
        Source("a", "법", "과태료를 부과할 수 있다.", "제33조", "카드", "과태료를 부과할 수 있다.")
    ]
    ok = SummaryResult(True, None, [SummaryLine("과태료를 부과할 수 있다고 합니다.", ("a",))])
    assert verify_summary(ok, in_source) == []


def test_the_prompt_states_the_clarification_and_out_of_doc_rules():
    from app.agent.summarizer import SUMMARY_SYSTEM

    for phrase in (
        "초과될 것 같은데 어떡해요",
        "기록은 얼마나 보관해야 해",
        "허가 취소 요건",
        "미국 EPA",
        "먼지",
    ):
        assert phrase in SUMMARY_SYSTEM
    assert "no_doc" in SUMMARY_SYSTEM and "need_clarification" in SUMMARY_SYSTEM


def test_grounded_summarizer_request_has_card_mode_text():
    cards = all_cards()
    chunk = BY_ID["law-279785-article-34"]
    source = Source(
        chunk.id,
        chunk.doc_title,
        chunk.text[:100],
        chunk.article,
        cards[chunk.id].brief(),
        chunk.text,
    )
    request = GroundedSummarizer(client=None, model_id="m").request("조업정지가 뭐예요", [source])
    text = request["messages"][0]["content"][0]["text"]
    assert text.startswith("[질문]") and "[후보 카드]" in text and "[핵심 원문]" in text


def test_build_index_command_writes_a_loadable_tfidf_index(tmp_path):
    from app.agent.build_index import load_chunks, main

    chunks, _version = load_chunks()
    assert len(chunks) == len(CHUNKS)
    out = tmp_path / "idx.json"
    assert main(["--out", str(out), "--cards", str(tmp_path / "없는 카드 파일.json")]) == 0
    cards, _ = load_cards(chunks, tmp_path / "없는 카드 파일.json")
    index = load_index(out, cards_fingerprint(cards))
    assert index.kind == "char-ngram-tfidf-v1" and len(index.ids) == len(chunks)


def test_the_shipped_tfidf_index_matches_the_current_cards():
    """저장소의 색인 파일이 지금 카드와 맞는다(카드를 바꾸면 build_index를 다시 돌린다)."""
    from app.agent.vindex import DEFAULT_TFIDF_INDEX

    index = load_index(DEFAULT_TFIDF_INDEX, cards_fingerprint(all_cards()))
    assert set(index.ids) == {c.id for c in CHUNKS}
