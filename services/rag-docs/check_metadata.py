"""업로드 폴더의 PDF·메타데이터 짝을 올리기 전에 검사한다 (spec 016 FR-007, SC-002).

  python check_metadata.py --dest <업로드 폴더>

검사: 짝 존재 · 파일명 · JSON · 최상위 키 · 값 타입(STRING/NUMBER/BOOLEAN/STRING_LIST) · 빈 값 ·
includeForEmbedding 대상 · 필수 키 · 10KB 이하 · page_count = PDF 쪽수 · doc_id 유일 · PDF·JSON 외 파일 없음.
실패마다 "파일: 이유" 한 줄, 끝에 "통과 N/M". 실패가 있으면 종료 코드 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

import catalog as cat


def check_value(key: str, attr: object) -> list[str]:
    if not isinstance(attr, dict) or "value" not in attr:
        return [f"{key}: value 없음"]
    errs: list[str] = []
    v = attr["value"]
    typ = v.get("type") if isinstance(v, dict) else None
    if typ not in cat.TYPES:
        return [f"{key}: 허용되지 않는 타입 {typ!r}"]
    field = {"STRING": "stringValue", "NUMBER": "numberValue",
             "BOOLEAN": "booleanValue", "STRING_LIST": "stringListValue"}[typ]
    x = v.get(field)
    if x is None:
        errs.append(f"{key}: {field} 없음(null 불가)")
    elif typ == "STRING" and (not isinstance(x, str) or not x.strip()):
        errs.append(f"{key}: 빈 문자열")
    elif typ == "NUMBER" and (isinstance(x, bool) or not isinstance(x, (int, float))):
        errs.append(f"{key}: 숫자 아님")
    elif typ == "BOOLEAN" and not isinstance(x, bool):
        errs.append(f"{key}: 참거짓 아님")
    elif typ == "STRING_LIST" and (not isinstance(x, list) or not x
                                   or not all(isinstance(i, str) and i.strip() for i in x)):
        errs.append(f"{key}: 빈 목록 또는 빈 항목")
    emb = attr.get("includeForEmbedding")
    if not isinstance(emb, bool):
        errs.append(f"{key}: includeForEmbedding 없음")
    elif emb != (key in cat.EMBED_KEYS):
        errs.append(f"{key}: includeForEmbedding는 {key in cat.EMBED_KEYS}여야 함")
    if key.startswith("x-amz-bedrock-kb-"):
        errs.append(f"{key}: 예약된 접두어")
    return errs


def check_pair(pdf: Path, pages: Callable[[Path], int] = cat.pdf_pages) -> tuple[list[str], str | None]:
    """(오류 목록, doc_id)"""
    meta = pdf.with_name(cat.metadata_name(pdf.name))
    if not meta.is_file():
        return [f"짝 없음 — {meta.name} 필요"], None
    size = meta.stat().st_size
    errs: list[str] = []
    if size > cat.MAX_BYTES:
        errs.append(f"크기 {size}B > {cat.MAX_BYTES}B")
    try:
        body = json.loads(meta.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return errs + [f"JSON 오류: {e}"], None
    if not isinstance(body, dict) or set(body) != {"metadataAttributes"}:
        return errs + ["최상위는 metadataAttributes 하나만"], None
    attrs = body["metadataAttributes"]
    if not isinstance(attrs, dict):
        return errs + ["metadataAttributes가 객체가 아님"], None
    for key, attr in attrs.items():
        errs += check_value(key, attr)
    for key in cat.REQUIRED_KEYS:
        if key not in attrs:
            errs.append(f"필수 키 없음: {key}")
    doc_id = attrs.get("doc_id", {}).get("value", {}).get("stringValue")
    want = attrs.get("page_count", {}).get("value", {}).get("numberValue")
    if isinstance(want, int):
        got = pages(pdf)
        if got != want:
            errs.append(f"page_count {want} ≠ PDF {got}쪽")
    return errs, doc_id


def check_dest(dest: Path, pages: Callable[[Path], int] = cat.pdf_pages) -> tuple[list[str], int, int]:
    """(실패 줄, 통과 수, PDF 수)"""
    lines: list[str] = []
    pdfs: list[Path] = []
    for p in sorted(dest.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(dest).as_posix()
        if rel.split("/", 1)[0] not in cat.FOLDERS:
            lines.append(f"{rel}: 데이터 소스 폴더(laws/·handbook/) 밖의 파일")
        elif p.name.endswith(".pdf"):
            pdfs.append(p)
        elif p.name.endswith(cat.SUFFIX):
            if not p.with_name(p.name[: -len(cat.SUFFIX)]).is_file():
                lines.append(f"{rel}: 짝 PDF 없음")
        else:
            lines.append(f"{rel}: PDF·메타데이터 외 파일(문서로 색인됨)")
    ok = 0
    ids: dict[str, str] = {}
    for pdf in pdfs:
        rel = pdf.relative_to(dest).as_posix()
        errs, doc_id = check_pair(pdf, pages)
        if doc_id:
            if doc_id in ids:
                errs.append(f"doc_id 중복 ({ids[doc_id]})")
            ids.setdefault(doc_id, rel)
        if errs:
            lines += [f"{rel}: {e}" for e in errs]
        else:
            ok += 1
    return lines, ok, len(pdfs)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dest", type=Path, required=True)
    a = p.parse_args(argv)
    lines, ok, total = check_dest(a.dest)
    for line in lines:
        print(line)
    print(f"통과 {ok}/{total}")
    return 0 if not lines and total else 1


if __name__ == "__main__":
    sys.exit(main())
