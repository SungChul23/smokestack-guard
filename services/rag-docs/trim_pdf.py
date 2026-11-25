"""PDF 쪽 범위를 잘라 새 파일로 만든다 (spec 016 FR-008, research R7). 원본은 읽기만 한다.

  python trim_pdf.py <원본.pdf> --pages 21-55 --out <새 파일.pdf>

시행규칙 별표 8: 1~20쪽(과 21쪽 앞부분)은 2019-12-31까지 적용된 과거 기준, 21~55쪽이 2020-01-01부터의 현행 기준이다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_range(text: str) -> tuple[int, int]:
    try:
        a, b = (int(x) for x in text.split("-", 1))
    except ValueError as e:
        raise ValueError(f"쪽 범위는 A-B 형식이다: {text!r}") from e
    if a < 1 or b < a:
        raise ValueError(f"쪽 범위가 잘못됐다: {text!r}")
    return a, b


def trim(src: Path, first: int, last: int, out: Path) -> int:
    from pypdf import PdfReader, PdfWriter

    if src.resolve() == out.resolve():
        raise ValueError("출력 파일이 원본과 같다 — 원본은 바꾸지 않는다")
    reader = PdfReader(str(src))
    if last > len(reader.pages):
        raise ValueError(f"원본은 {len(reader.pages)}쪽인데 {last}쪽까지 요청했다")
    writer = PdfWriter()
    for i in range(first - 1, last):
        writer.add_page(reader.pages[i])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        writer.write(f)
    return last - first + 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("src", type=Path)
    p.add_argument("--pages", required=True, help="예: 21-55")
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args(argv)
    try:
        first, last = parse_range(a.pages)
        n = trim(a.src, first, last, a.out)
    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    print(f"{a.out} ({n}쪽, 원본 {first}~{last}쪽)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
