"""PDF를 쪽마다 Claude(Sonnet 4.6)로 마크다운으로 옮기고, 검사를 통과한 결과만 문서 하나의 .md로 만든다
(spec 016, research R4b).

  python pdf_to_md.py --src <업로드 폴더(PDF)> --dest <md 폴더> --dry-run      # 쪽 수·예상 비용만
  python pdf_to_md.py --src … --dest …                                         # 전체(끝난 쪽은 건너뜀)
  python pdf_to_md.py --src … --dest … --doc air-rule_appx-36 --redo            # 한 문서 다시

- 쪽을 150dpi 그림으로 렌더링해 parsing_prompt.md 지시문과 함께 모델에 보낸다(2026-11-23 별표 36에서 정확했던 조건).
- 쪽마다 바로 검사한다: 표 칸 수(머리글과 본문), 법제처 머리글 잔존, 겹친 글자. 걸리면 그 쪽만 다시(--tries).
- 쪽별 결과를 cache/<doc_id>/에 저장한다. 다시 실행하면 끝난 쪽은 건너뛴다(중간에 끊겨도 이어서).
- 결과: <dest>/<folder>/<PDF 이름>.md (쪽 표시 "<!-- 쪽 N -->" 포함). 이름표는 make_metadata.py --format md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import catalog as cat
import check_chunks as cc

MODEL = "global.anthropic.claude-sonnet-4-6"
PROMPT = cat.HERE / "parsing_prompt.md"
CACHE = cat.HERE / "cache"
DPI = 150
# 단가(USD/100만 토큰) — 예상 비용 표시용. Sonnet 4.6 = Sonnet 등급 가정
PRICE_IN, PRICE_OUT = 3.0, 15.0
PAGE_MARK = "<!-- 쪽 {n} -->"


def clean_page(text: str) -> str:
    """빈 쪽에서 모델이 본문 대신 남긴 영어 설명("The image appears to be blank…")은 빈 쪽으로 둔다."""
    if cc.MODEL_NOTE.search(text) and not re.search(r"[가-힣]", text):
        return ""
    return text


def page_problems(text: str) -> list[str]:
    probs = [f"칸: {r}" for r in cc.misaligned_rows(text)]
    if cc.MODEL_NOTE.search(text):
        probs.append("모델 메모 잔존")
    if "국가법령정보센터" in text:
        probs.append("머리글 잔존")
    probs += [f"겹친 글자: {m.group(0)}" for m in cc.DOUBLED.finditer(text)]
    return probs


def render(pdf: Path, index: int, dpi: int = DPI) -> bytes:
    import pymupdf

    with pymupdf.open(pdf) as d:
        return d[index].get_pixmap(dpi=dpi).tobytes("png")


def page_count(pdf: Path) -> int:
    import pymupdf

    with pymupdf.open(pdf) as d:
        return d.page_count


@dataclass
class PageResult:
    text: str
    problems: list[str]
    tries: int
    tokens_in: int
    tokens_out: int


def convert_page(client, model: str, prompt: str, png: bytes, tries: int) -> PageResult:
    """검사에 걸리면 다시 부른다. 끝까지 걸리면 문제가 가장 적은 결과를 쓴다."""
    best: PageResult | None = None
    tin = tout = 0
    for i in range(1, tries + 1):
        r = client.converse(
            modelId=model,
            messages=[{"role": "user", "content": [
                {"image": {"format": "png", "source": {"bytes": png}}}, {"text": prompt}]}],
            inferenceConfig={"maxTokens": 8000},
        )
        text = r["output"]["message"]["content"][0]["text"].strip()
        tin += r["usage"]["inputTokens"]
        tout += r["usage"]["outputTokens"]
        probs = page_problems(text)
        if best is None or len(probs) < len(best.problems):
            best = PageResult(text, probs, i, 0, 0)
        if not probs:
            break
    assert best is not None
    best.tries, best.tokens_in, best.tokens_out = i, tin, tout
    return best


def cache_path(cache: Path, doc_id: str, page: int) -> Path:
    return cache / doc_id / f"p{page:04d}.json"


def convert_doc(doc: cat.Doc, src: Path, cache: Path, client, model: str, prompt: str,
                tries: int, workers: int, redo: bool, log=print) -> list[dict]:
    pdf = src / doc.folder / doc.file
    n = page_count(pdf)

    def one(i: int) -> dict:
        path = cache_path(cache, doc.doc_id, i + 1)
        if path.is_file() and not redo:
            return json.loads(path.read_text(encoding="utf-8"))
        res = convert_page(client, model, prompt, render(pdf, i), tries)
        rec = {"page": i + 1, "text": res.text, "problems": res.problems, "tries": res.tries,
               "tokens_in": res.tokens_in, "tokens_out": res.tokens_out, "model": model}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        flag = f" !! {len(res.problems)}건" if res.problems else ""
        log(f"  {doc.doc_id} {i + 1}/{n}쪽 (시도 {res.tries}){flag}")
        return rec

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, range(n)))


def assemble(pages: list[dict]) -> str:
    parts = []
    for p in sorted(pages, key=lambda x: x["page"]):
        parts.append(PAGE_MARK.format(n=p["page"]))
        text = clean_page(p["text"])
        if text:
            parts.append(text)
    return "\n\n".join(parts) + "\n"


def md_path(dest: Path, doc: cat.Doc) -> Path:
    return dest / doc.folder / cat.md_name(doc.file)


def client_for(region: str = "ap-northeast-2"):
    import boto3
    from botocore.config import Config

    return boto3.client("bedrock-runtime", region_name=region,
                        config=Config(read_timeout=300, retries={"max_attempts": 10, "mode": "adaptive"}))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--src", type=Path, required=True, help="PDF 업로드 폴더(laws/·handbook/)")
    p.add_argument("--dest", type=Path, required=True, help="md를 쓸 폴더(laws/·handbook/)")
    p.add_argument("--catalog", type=Path, default=cat.CATALOG)
    p.add_argument("--cache", type=Path, default=CACHE)
    p.add_argument("--doc", action="append", help="doc_id (여러 번 가능). 없으면 전체")
    p.add_argument("--model", default=MODEL)
    p.add_argument("--tries", type=int, default=3)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--redo", action="store_true", help="캐시를 무시하고 다시 변환")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    docs = cat.read_catalog(a.catalog)
    if a.doc:
        unknown = set(a.doc) - {d.doc_id for d in docs}
        if unknown:
            print(f"오류: 원장에 없는 doc_id {sorted(unknown)}", file=sys.stderr)
            return 2
        docs = [d for d in docs if d.doc_id in a.doc]
    pages = {d.doc_id: page_count(a.src / d.folder / d.file) for d in docs}
    todo = sum(n for d in docs for n in [pages[d.doc_id]]
               if a.redo or not all(cache_path(a.cache, d.doc_id, i).is_file() for i in range(1, n + 1)))
    est = todo * (2000 * PRICE_IN + 1300 * PRICE_OUT) / 1e6
    print(f"문서 {len(docs)}개, {sum(pages.values())}쪽 (변환할 쪽 약 {todo}), 예상 약 ${est:.1f} ({a.model})")
    if a.dry_run:
        return 0

    prompt = PROMPT.read_text(encoding="utf-8")
    client = client_for()
    total_in = total_out = 0
    flagged: list[str] = []
    t0 = time.time()
    for d in docs:
        recs = convert_doc(d, a.src, a.cache, client, a.model, prompt, a.tries, a.workers, a.redo)
        out = md_path(a.dest, d)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(assemble(recs), encoding="utf-8")
        total_in += sum(r["tokens_in"] for r in recs)
        total_out += sum(r["tokens_out"] for r in recs)
        bad = [r for r in recs if r["problems"]]
        flagged += [f"{d.doc_id} {r['page']}쪽: {r['problems'][0][:90]}" for r in bad]
        print(f"{'!!' if bad else 'OK'} {d.doc_id:<32} {len(recs):4}쪽  문제 쪽 {len(bad)}  → {out.name}")
    cost = (total_in * PRICE_IN + total_out * PRICE_OUT) / 1e6
    print(f"\n토큰 입력 {total_in:,} / 출력 {total_out:,}  (이번 실행 약 ${cost:.2f}, 캐시 재사용분 포함), "
          f"{time.time() - t0:.0f}초")
    for f in flagged:
        print("  확인:", f)
    print("다음: make_metadata.py --format md → check_metadata.py → check_chunks.py --local <dest>")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
