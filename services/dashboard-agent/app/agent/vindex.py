"""로컬 벡터 색인: 카드를 벡터로 바꿔 파일로 저장하고, 질문과 가까운 카드를 찾는다.

별도 벡터 DB 서버를 쓰지 않는다(자료가 작아 전체 비교로 충분하다). 두 종류의 벡터를 같은 파일 형식으로 둔다.
- `char-ngram-tfidf-v1`: 한글 낱말의 문자 2·3-gram TF-IDF 벡터(표준 라이브러리만). **신경망 임베딩이 아니며
  의미 검색이 아니다.** 글자 조각이 겹치는 정도를 코사인으로 잰다.
- `neural-fastembed`: 로컬에서 돌리는 신경망 임베딩(FastEmbed ONNX 다국어 MiniLM). 질문을 벡터로 바꾸려면
  fastembed와 모델 캐시가 필요하다. 없으면 이 벡터는 쓰지 않고 TF-IDF·키워드로 찾는다.
색인에는 종류·모델·카드 지문(fingerprint)을 적고, 카드가 바뀌면 맞지 않는다고 판단해 다시 만든다.
이 모듈은 표준 라이브러리만 쓴다.
설계: specs/d-analytics/315-doc-summary-answer/
"""

# ruff: noqa: E501  (한글 설명·프롬프트 문장은 폭이 넓어 줄 길이 제한에 걸린다)
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

TFIDF_KIND = "char-ngram-tfidf-v1"
NEURAL_KIND = "neural-fastembed"
NEURAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_TFIDF_INDEX = Path(__file__).parent / "corpus" / "law-evidence-index-tfidf.json"
DEFAULT_NEURAL_INDEX = Path(__file__).parent / "corpus" / "law-evidence-index-neural.json"

Vector = dict[str, float] | list[float]


class IndexError_(RuntimeError):
    """색인을 쓸 수 없다(없음·지문 불일치·형식 오류)."""


def ngrams(text: str, sizes: tuple[int, ...] = (2, 3)) -> list[str]:
    """한글·영숫자 낱말 안에서 문자 조각을 만든다(낱말 경계는 넘지 않는다)."""
    folded = unicodedata.normalize("NFKC", text).lower()
    out: list[str] = []
    for word in re.findall(r"[가-힣a-z0-9]+", folded):
        if len(word) == 1:
            out.append(word)
            continue
        for n in sizes:
            out += [word[i : i + n] for i in range(len(word) - n + 1)]
    return out


def _normalize(vec: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return {k: v / norm for k, v in vec.items()} if norm else {}


def cosine(a: Vector, b: Vector) -> float:
    """정규화된 두 벡터의 코사인(내적). 희소(dict)·밀집(list) 모두 받는다."""
    if isinstance(a, dict) and isinstance(b, dict):
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(k, 0.0) for k, v in a.items())
    if isinstance(a, list) and isinstance(b, list):
        return sum(x * y for x, y in zip(a, b, strict=True))
    raise IndexError_("벡터 종류가 맞지 않는다")


@dataclass
class VectorIndex:
    kind: str
    model: str
    fingerprint: str  # 카드(색인 글) 지문
    ids: list[str]
    vectors: list[Vector]
    idf: dict[str, float] | None = None  # TF-IDF 전용
    dims: int = 0

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind, "model": self.model, "fingerprint": self.fingerprint,
            "ids": self.ids, "dims": self.dims,
            "vectors": [
                {k: round(v, 5) for k, v in vec.items()} if isinstance(vec, dict)
                else [round(x, 5) for x in vec]
                for vec in self.vectors
            ],
        }  # fmt: skip
        if self.idf is not None:
            data["idf"] = {k: round(v, 5) for k, v in self.idf.items()}
        return data

    def query_vector(self, text: str) -> dict[str, float]:
        """TF-IDF 색인의 질문 벡터(학습에 쓴 idf만 쓴다)."""
        if self.kind != TFIDF_KIND or self.idf is None:
            raise IndexError_("이 색인은 TF-IDF가 아니다")
        counts = Counter(ngrams(text))
        return _normalize(
            {g: (1 + math.log(c)) * self.idf[g] for g, c in counts.items() if g in self.idf}
        )

    def scores(self, query_vec: Vector) -> list[tuple[str, float]]:
        pairs = [(i, cosine(query_vec, v)) for i, v in zip(self.ids, self.vectors, strict=True)]
        pairs.sort(key=lambda p: p[1], reverse=True)
        return pairs


def build_tfidf_index(texts: dict[str, str], fingerprint: str) -> VectorIndex:
    """카드 글(id → 색인 글)로 TF-IDF 색인을 만든다."""
    ids = sorted(texts)
    counts = {i: Counter(ngrams(texts[i])) for i in ids}
    df: Counter[str] = Counter()
    for c in counts.values():
        df.update(c.keys())
    n = len(ids)
    idf = {g: math.log((1 + n) / (1 + d)) + 1.0 for g, d in df.items()}
    vectors: list[Vector] = [
        _normalize({g: (1 + math.log(c)) * idf[g] for g, c in counts[i].items()}) for i in ids
    ]
    return VectorIndex(TFIDF_KIND, "char 2-3gram tf-idf", fingerprint, ids, vectors, idf, len(idf))


def build_dense_index(
    ids: list[str], vectors: list[list[float]], model: str, fingerprint: str
) -> VectorIndex:
    out: list[Vector] = []
    for v in vectors:
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return VectorIndex(
        NEURAL_KIND, model, fingerprint, list(ids), out, None, len(out[0]) if out else 0
    )


def save_index(index: VectorIndex, path: Path) -> None:
    path.write_text(json.dumps(index.to_json(), ensure_ascii=False), encoding="utf-8")


def load_index(path: Path, fingerprint: str) -> VectorIndex:
    """색인을 읽는다. 없거나 카드 지문이 다르면 IndexError_ (부르는 쪽이 다시 만들거나 대체한다)."""
    if not path.exists():
        raise IndexError_(f"색인 파일이 없다: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        index = VectorIndex(
            data["kind"], data["model"], data["fingerprint"], list(data["ids"]),
            [v for v in data["vectors"]], data.get("idf"), int(data.get("dims") or 0),
        )  # fmt: skip
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise IndexError_(f"색인 파일을 읽을 수 없다: {path.name}") from error
    if index.fingerprint != fingerprint:
        raise IndexError_("색인이 현재 카드와 맞지 않는다(카드가 바뀌었다). 다시 만들어야 한다")
    if len(index.ids) != len(index.vectors):
        raise IndexError_("색인 파일이 손상됐다")
    return index


# ── 질문 임베딩(신경망) ────────────────────────────────────────────────────
class Embedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


class EmbedderUnavailable(RuntimeError):
    """신경망 임베딩을 쓸 수 없다(패키지·모델 캐시 없음)."""


class FastEmbedEmbedder:
    """로컬 FastEmbed ONNX 모델로 질문을 벡터로 바꾼다. 모델을 내려받지 않는다(local_files_only).

    환경 변수 TMS_EMBED_CACHE에 모델 캐시 폴더를 준다. fastembed가 설치돼 있지 않거나 캐시가 없으면
    EmbedderUnavailable을 낸다(서비스는 그때 TF-IDF·키워드로 찾고 그 사실을 안내한다).
    """

    def __init__(self, cache_dir: str | None = None, model: str = NEURAL_MODEL) -> None:
        cache = cache_dir or os.environ.get("TMS_EMBED_CACHE")
        if not cache or not Path(cache).exists():
            raise EmbedderUnavailable("모델 캐시 폴더가 지정되지 않았거나 없다(TMS_EMBED_CACHE)")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
        try:
            from fastembed import TextEmbedding  # type: ignore[import-not-found]

            self._model = TextEmbedding(model_name=model, cache_dir=cache, local_files_only=True)
        except Exception as error:  # noqa: BLE001  패키지 없음·모델 없음·ONNX 오류 모두 같은 처리
            raise EmbedderUnavailable(
                f"신경망 임베딩을 불러오지 못했다: {type(error).__name__}"
            ) from error
        self.model = model

    def embed_query(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self._model.embed([text])))]


class PrecomputedEmbedder:
    """미리 계산한 질문 벡터를 돌려준다(시험용: 서비스 환경에 fastembed가 없을 때)."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def embed_query(self, text: str) -> list[float]:
        try:
            return self._vectors[text]
        except KeyError as error:
            raise EmbedderUnavailable("미리 계산한 질문 벡터에 없는 질문이다") from error
