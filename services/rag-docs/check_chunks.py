"""동기화 뒤 OpenSearch rag-docs 조각 품질을 문서별로 검사한다 (spec 016, research R4a).

  python check_chunks.py                  # 전체 문서
  python check_chunks.py --doc air-rule_appx-36
  python check_chunks.py --local <md 폴더>     # 올리기 전: pdf_to_md.py가 만든 md와 이름표로 검사

검사
  - 표 칸 어긋남: 마크다운 표에서 머리글과 칸 수가 다른 행 (파서가 칸을 빼거나 밀었을 가능성)
  - 머리글 잔존: "국가법령정보센터"가 남은 조각
  - 겹친 글자: "굴굴뚝뚝"처럼 같은 글자가 두 번씩 이어진 구간
  - 정답 행(golden_rows.yaml): 원본에서 확인한 행이 그대로 있는지
문제가 있는 문서는 S3에 같은 파일을 다시 올리고 동기화하면 그 문서만 다시 파싱된다.

도메인 마스터 IAM 사용자로 실행한다(members 뷰어는 메타데이터 조회는 되지만 이 스크립트는 SigV4 서명 요청).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGION = "ap-northeast-2"
DOMAIN = "tms-logs"
INDEX = "rag-docs"
DOUBLED = re.compile(r"(?:([가-힣])\1){2,}")  # 같은 한글이 두 번씩 2글자 이상 이어짐(굴굴뚝뚝)
# 변환 모델이 본문 대신 남긴 영어 설명(빈 쪽에서 "The image appears to be blank…", 2026-11-24 편람 10쪽)
MODEL_NOTE = re.compile(r"The image (?:appears|is|contains)|I cannot (?:transcribe|detect|read)|no visible text", re.IGNORECASE)


@dataclass
class Report:
    doc_id: str
    chunks: int = 0
    table_rows: int = 0
    misaligned: list[str] = field(default_factory=list)
    header_left: int = 0
    doubled: list[str] = field(default_factory=list)
    golden_fail: list[str] = field(default_factory=list)
    model_note: int = 0

    @property
    def ok(self) -> bool:
        return not (self.misaligned or self.header_left or self.doubled or self.golden_fail or self.model_note)


def table_blocks(text: str) -> list[list[str]]:
    blocks, cur = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cur.append(line.strip())
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def is_rule(row: str) -> bool:
    return bool(re.fullmatch(r"\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*\|?", row))


def misaligned_rows(text: str) -> list[str]:
    bad = []
    for block in table_blocks(text):
        if len(block) < 2:
            continue
        width = len(cells(block[0]))
        for row in block[1:]:
            if not is_rule(row) and len(cells(row)) != width:
                bad.append(row[:120])
    return bad


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def has_row(text: str, want: list[str]) -> bool:
    """want의 값들이 한 표 행 안에 이 순서로 (빈 칸은 무시하고) 연속해 있는가."""
    target = [norm(w) for w in want]
    for block in table_blocks(text):
        for row in block:
            got = [norm(c) for c in cells(row) if norm(c)]
            first = next((i for i, g in enumerate(got) if target[0] in g), None)
            if first is not None and got[first + 1:first + len(target)] == target[1:]:
                return True
    return False


def load_golden(path: Path) -> dict[str, list[dict]]:
    if not path.is_file():
        return {}
    import yaml

    return {d["doc_id"]: d["rows"] for d in yaml.safe_load(path.read_text(encoding="utf-8")) or []}


def evaluate(hits: list[dict], golden: dict[str, list[dict]]) -> dict[str, Report]:
    """hits: OpenSearch _source 목록(doc_id, bedrock-text, bedrock-metadata)."""
    reports: dict[str, Report] = {}
    texts: dict[str, set[str]] = defaultdict(set)
    for src in hits:
        doc = src.get("doc_id") or "?"
        r = reports.setdefault(doc, Report(doc))
        r.chunks += 1
        texts[doc].add(src.get("bedrock-text", ""))
        meta = src.get("bedrock-metadata")
        if meta:
            try:
                parent = json.loads(meta).get("parentText")
            except ValueError:
                parent = None
            if parent:
                texts[doc].add(parent)
    for doc, ts in texts.items():
        r = reports[doc]
        for t in ts:
            for block in table_blocks(t):
                r.table_rows += sum(1 for row in block[1:] if not is_rule(row))
            for row in misaligned_rows(t):
                if row not in r.misaligned:
                    r.misaligned.append(row)
            if "국가법령정보센터" in t:
                r.header_left += 1
            r.model_note += bool(MODEL_NOTE.search(t))
            for m in DOUBLED.finditer(t):
                r.doubled.append(m.group(0))
        for g in golden.get(doc, []):
            if not any(has_row(t, g["cells"]) for t in ts):
                r.golden_fail.append(g["label"])
    return reports


def fetch(doc: str | None) -> list[dict]:
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    ses = boto3.Session(region_name=REGION)
    ep = ses.client("opensearch").describe_domain(DomainName=DOMAIN)["DomainStatus"]["Endpoint"]
    signer = SigV4Auth(ses.get_credentials(), "es", REGION)

    def call(path: str, body: dict) -> dict:
        data = json.dumps(body).encode()
        req = AWSRequest(method="POST", url=f"https://{ep}{path}", data=data,
                         headers={"Content-Type": "application/json"})
        signer.add_auth(req)
        r = urllib.request.Request(req.url, data=data, method="POST", headers=dict(req.headers))
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise SystemExit(f"OpenSearch {e.code}: {e.read()[:300]!r}") from e

    query = {"term": {"doc_id.keyword": doc}} if doc else {"match_all": {}}
    body = {"size": 1000, "query": query, "sort": ["_doc"],
            "_source": ["doc_id", "bedrock-text", "bedrock-metadata"]}
    out, after = [], None
    while True:
        if after:
            body["search_after"] = after
        hits = call(f"/{INDEX}/_search", body)["hits"]["hits"]
        out += [h["_source"] for h in hits]
        if len(hits) < body["size"]:
            return out
        after = hits[-1]["sort"]


def local_hits(folder: Path, doc: str | None = None) -> list[dict]:
    """올리기 전 검사: md 문서 하나 = 조각 하나로 보고, doc_id는 이름표에서 읽는다."""
    hits = []
    for md in sorted(folder.rglob("*.md")):
        meta = md.with_name(md.name + ".metadata.json")
        doc_id = md.stem
        if meta.is_file():
            attrs = json.loads(meta.read_text(encoding="utf-8"))["metadataAttributes"]
            doc_id = attrs.get("doc_id", {}).get("value", {}).get("stringValue", doc_id)
        if doc is None or doc == doc_id:
            hits.append({"doc_id": doc_id, "bedrock-text": md.read_text(encoding="utf-8")})
    return hits


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--doc", help="doc_id 하나만")
    p.add_argument("--local", type=Path, help="OpenSearch 대신 이 폴더의 md를 검사")
    p.add_argument("--golden", type=Path, default=HERE / "golden_rows.yaml")
    p.add_argument("--show", type=int, default=3, help="문서마다 보여 줄 어긋난 행 수")
    a = p.parse_args(argv)
    hits = local_hits(a.local, a.doc) if a.local else fetch(a.doc)
    reports = evaluate(hits, load_golden(a.golden))
    bad = 0
    for doc in sorted(reports):
        r = reports[doc]
        mark = "OK " if r.ok else "!! "
        bad += not r.ok
        print(f"{mark}{doc:<32} 조각 {r.chunks:4}  표 행 {r.table_rows:4}  칸 어긋남 {len(r.misaligned):3}"
              f"  머리글 {r.header_left}  겹친 글자 {len(r.doubled)}  정답 실패 {len(r.golden_fail)}"
              + (f"  모델 메모 {r.model_note}" if r.model_note else ""))
        for row in r.misaligned[: a.show]:
            print(f"      칸: {row}")
        for g in r.golden_fail:
            print(f"      정답 행 없음: {g}")
        for d in r.doubled[:2]:
            print(f"      겹친 글자: {d}")
    print(f"\n문서 {len(reports)}개 중 확인 필요 {bad}개")
    if bad:
        print("다시 파싱: 그 문서 PDF를 S3에 다시 올리고(aws s3 cp) 데이터 소스를 동기화한다")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
