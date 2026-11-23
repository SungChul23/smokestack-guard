"""원장 → 문서마다 <파일>.metadata.json (spec 016 FR-002~FR-007, contracts/metadata-file.md).

  python make_metadata.py --dest <업로드 폴더>

- 원장에서 빈 칸은 "확인 안 됨"이다. 메타데이터에 넣지 않고 missing_fields.csv(저장소)에 적는다.
- PDF는 읽기만 한다(쪽수 확인은 check_metadata.py).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import catalog as cat

MISSING = cat.HERE / "missing_fields.csv"
# 문서마다 확인하지 않은 것이 정상인 키(빠진 목록에 넣지 않음)
OPTIONAL = {"amendment_mark", "caveat"}


def write_all(docs: list[cat.Doc], dest: Path, missing_out: Path) -> int:
    rows: list[tuple[str, str]] = []
    for d in docs:
        pdf = dest / d.folder / d.file
        if not pdf.is_file():
            raise FileNotFoundError(f"업로드 폴더에 없음: {d.folder}/{d.file}")
        body, missing = cat.to_metadata(d)
        out = pdf.with_name(cat.metadata_name(d.file))
        out.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rows += [(d.doc_id, k) for k in missing if k not in OPTIONAL]
    for folder in cat.FOLDERS:
        listed = {d.file for d in docs if d.folder == folder}
        for pdf in sorted((dest / folder).glob("*.pdf")) if (dest / folder).is_dir() else []:
            if pdf.name not in listed:
                raise ValueError(f"원장에 없는 PDF: {folder}/{pdf.name}")
    with missing_out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "missing_key"])
        w.writerows(rows)
    return len(docs)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dest", type=Path, required=True)
    p.add_argument("--catalog", type=Path, default=cat.CATALOG)
    p.add_argument("--missing", type=Path, default=MISSING)
    a = p.parse_args(argv)
    try:
        n = write_all(cat.read_catalog(a.catalog), a.dest, a.missing)
    except (ValueError, FileNotFoundError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    print(f"메타데이터 {n}개 생성, 빠진 항목 목록 → {a.missing}")
    print("다음: python check_metadata.py --dest", a.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
