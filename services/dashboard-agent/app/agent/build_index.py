# ruff: noqa: E501  (한글 설명 문장은 폭이 넓어 줄 길이 제한에 걸린다)
"""근거 색인 만들기: 카드 → 벡터 색인 파일(corpus/law-evidence-index-*.json).

사용 (프로젝트 루트에서):
  uv run --project services/dashboard-agent python -m app.agent.build_index
      → 글자 조각 TF-IDF 색인(표준 라이브러리만). 서비스가 기본으로 쓴다.
  D/law-vector/.venv/Scripts/python.exe -m app.agent.build_index --neural --cache D/law-vector/cache
      → 신경망 임베딩(FastEmbed ONNX 다국어 MiniLM) 색인. fastembed와 로컬 모델 캐시가 있는 환경에서만.
카드가 바뀌면(카드 파일 교체·원문 변경) 카드 지문이 달라져 기존 색인은 쓰지 않으므로 다시 만든다.
이 모듈은 cards.py·vindex.py(표준 라이브러리만)에만 의존한다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from app.agent.cards import DEFAULT_CARDS, cards_fingerprint, load_cards
from app.agent.vindex import (
    DEFAULT_NEURAL_INDEX,
    DEFAULT_TFIDF_INDEX,
    NEURAL_KIND,
    NEURAL_MODEL,
    FastEmbedEmbedder,
    build_dense_index,
    build_tfidf_index,
    save_index,
)

DEFAULT_CORPUS = Path(__file__).parent / "corpus" / "law-evidence-20261112.json"


def load_chunks(path: Path = DEFAULT_CORPUS) -> tuple[list[SimpleNamespace], str]:
    """코퍼스 JSON에서 조문 목록을 읽는다(evidence.load_corpus와 같은 제목·조각 규칙)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    supplement = data.get("supplements") or {}
    titles = {d["id"]: d.get("title") or d.get("name") or d["id"] for d in data["documents"]}
    titles.update({d["id"]: d.get("title") or d["id"] for d in supplement.get("documents", [])})
    chunks = [
        SimpleNamespace(
            id=raw["id"],
            doc_title=titles.get(raw["document_id"], raw["document_id"]),
            article=raw.get("article") or "",
            heading=raw.get("heading") or "",
            text=raw["text"],
        )
        for raw in [*data["chunks"], *supplement.get("chunks", [])]
    ]
    return chunks, data["version"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--neural", action="store_true", help="신경망 임베딩 색인을 만든다")
    ap.add_argument(
        "--cache", default=os.environ.get("TMS_EMBED_CACHE"), help="로컬 모델 캐시 폴더"
    )
    ap.add_argument("--cards", default=str(DEFAULT_CARDS))
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    chunks, version = load_chunks()
    cards, report = load_cards(chunks, Path(args.cards))
    fp = cards_fingerprint(cards)
    print(
        f"코퍼스 {version}: 조문 {len(chunks)}개, 카드 LLM {report.llm} / 대체 {report.deterministic}"
    )
    for line in report.rejected:
        print("  카드 거절:", line)
    texts = {cid: card.index_text() for cid, card in cards.items()}

    if not args.neural:
        out = Path(args.out) if args.out else DEFAULT_TFIDF_INDEX
        index = build_tfidf_index(texts, fp)
        save_index(index, out)
        print(f"저장: {out.name} ({index.kind}, 조각 {index.dims}종, 카드 지문 {fp[:12]})")
        return 0

    embedder = FastEmbedEmbedder(args.cache)
    ids = sorted(texts)
    # 카드 글을 문서로 임베딩한다(질문과 같은 모델·같은 방식이라 embed_query를 쓴다)
    vectors = [embedder.embed_query(texts[i]) for i in ids]
    index = build_dense_index(ids, vectors, NEURAL_MODEL, fp)
    out = Path(args.out) if args.out else DEFAULT_NEURAL_INDEX
    save_index(index, out)
    print(f"저장: {out.name} ({NEURAL_KIND}, {index.dims}차원, 카드 지문 {fp[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
