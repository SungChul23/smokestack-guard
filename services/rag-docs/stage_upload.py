"""원장대로 업로드 폴더(laws/·handbook/)를 구성한다 (spec 016 US2, quickstart §3). S3에는 올리지 않는다.

  python stage_upload.py --src <원본 폴더> [<원본 폴더> …] --dest <업로드 폴더>

- 원장의 file을 원본 폴더들에서 찾아 <dest>/<folder>/로 복사한다.
- 이미 dest에 있는 파일(예: trim_pdf.py로 만든 별표 8 현행본)은 원본에서 찾지 않고 그대로 둔다.
- 원장에 없는 파일이 dest에 있으면 경고한다(문서로 색인되므로 지워야 한다).
- 끝에 실행할 aws s3 sync 명령(--dryrun)을 출력한다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import catalog as cat

BUCKET = "smokestack-tms-rag-952900391026"


def stage(docs: list[cat.Doc], srcs: list[Path], dest: Path) -> tuple[list[str], list[str]]:
    """(복사한 파일, 원장 밖 파일) — 원본을 찾지 못하면 FileNotFoundError."""
    copied: list[str] = []
    missing: list[str] = []
    for d in docs:
        target = dest / d.folder / d.file
        if target.exists():
            continue
        found = next((s / d.file for s in srcs if (s / d.file).is_file()), None)
        if found is None:
            missing.append(d.file)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(found, target)
        copied.append(f"{d.folder}/{d.file}")
    if missing:
        raise FileNotFoundError("원본에서 찾지 못함: " + ", ".join(missing))
    known = {f"{d.folder}/{d.file}" for d in docs}
    known |= {f"{d.folder}/{cat.metadata_name(d.file)}" for d in docs}
    extra = sorted(
        p.relative_to(dest).as_posix()
        for p in dest.rglob("*")
        if p.is_file() and p.relative_to(dest).as_posix() not in known
    )
    return copied, extra


def sync_command(dest: Path) -> str:
    return (f'aws s3 sync "{dest}" s3://{BUCKET}/ --exclude "*" --include "*.pdf" '
            f'--include "*{cat.SUFFIX}" --delete --dryrun')


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--src", nargs="+", type=Path, required=True)
    p.add_argument("--dest", type=Path, required=True)
    p.add_argument("--catalog", type=Path, default=cat.CATALOG)
    a = p.parse_args(argv)
    docs = cat.read_catalog(a.catalog)
    try:
        copied, extra = stage(docs, a.src, a.dest)
    except FileNotFoundError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    print(f"복사 {len(copied)}개, 원장 문서 {len(docs)}개")
    for f in extra:
        print(f"경고: 원장에 없는 파일 — 지우세요(문서로 색인됨): {f}")
    print("\n다음: make_metadata.py → check_metadata.py → 아래 명령(--dryrun 확인 뒤 빼고 실행)")
    print(sync_command(a.dest))
    return 1 if extra else 0


if __name__ == "__main__":
    sys.exit(main())
