"""문서 원장(docs_catalog.csv)과 메타데이터 파일 형식 (spec 016, data-model §1·§2, contracts/metadata-file.md).

make_metadata · check_metadata · stage_upload가 함께 쓰는 규칙을 한곳에 둔다.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "docs_catalog.csv"
SUFFIX = ".metadata.json"
MAX_BYTES = 10 * 1024  # 지식 기반 한도

FOLDERS = ("laws", "handbook")
EFFECTIVE_STATUS = ("현행", "구판", "과거")
AUTHORITY_CLASS = ("법률", "시행령", "시행규칙", "위임 고시", "훈령", "업무편람")
DOC_TYPE = ("법률", "시행령", "시행규칙", "고시", "훈령", "별표", "편람")
TMS_RELEVANCE = ("직접", "간접")

# 조각의 검색 내용(임베딩)에 함께 넣는 키. 같은 번호 별표(시행령 별표 8 ↔ 시행규칙 별표 8)를 구분한다
EMBED_KEYS = ("law_name", "title_ko", "part")
REQUIRED_KEYS = ("doc_id", "law_name", "title_ko", "part", "doc_type", "effective_date",
                 "effective_status", "authority_class", "page_count")
# 원장 열 → 메타데이터 키와 타입. 원장에만 있는 열: file, folder, notes_private
FIELDS: dict[str, str] = {
    "doc_id": "STRING",
    "law_name": "STRING",
    "title_ko": "STRING",
    "doc_type": "STRING",
    "part": "STRING",
    "doc_no": "STRING",
    "effective_date": "STRING",
    "amendment_mark": "STRING",
    "effective_status": "STRING",
    "authority_class": "STRING",
    "tms_relevance": "STRING",
    "source_org": "STRING",
    "related_articles": "STRING_LIST",
    "table_heavy": "BOOLEAN",
    "page_count": "NUMBER",
    "caveat": "STRING",
}
COLUMNS = ("file", "folder", *FIELDS, "notes_private")
TYPES = ("STRING", "NUMBER", "BOOLEAN", "STRING_LIST")

DOC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


@dataclass(frozen=True)
class Doc:
    row: dict[str, str]

    @property
    def file(self) -> str:
        return self.row["file"]

    @property
    def folder(self) -> str:
        return self.row["folder"]

    @property
    def doc_id(self) -> str:
        return self.row["doc_id"]


def read_catalog(path: Path = CATALOG) -> list[Doc]:
    """원장을 읽고 형식을 확인한다. 문제가 있으면 ValueError(행 번호와 이유)."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"원장 열이 다르다: {reader.fieldnames} != {list(COLUMNS)}")
        docs = [Doc({k: (v or "").strip() for k, v in r.items()}) for r in reader]
    errors: list[str] = []
    seen_id: set[str] = set()
    seen_file: set[str] = set()
    for i, d in enumerate(docs, start=2):
        r = d.row
        for k in ("file", "folder", *REQUIRED_KEYS):
            if not r[k]:
                errors.append(f"{i}행: {k} 비어 있음")
        checks = [
            ("folder", FOLDERS), ("effective_status", EFFECTIVE_STATUS),
            ("authority_class", AUTHORITY_CLASS), ("doc_type", DOC_TYPE),
        ]
        for col, allowed in checks:
            if r[col] and r[col] not in allowed:
                errors.append(f"{i}행: {col}={r[col]!r} (허용 {allowed})")
        if r["tms_relevance"] and r["tms_relevance"] not in TMS_RELEVANCE:
            errors.append(f"{i}행: tms_relevance={r['tms_relevance']!r}")
        if r["doc_id"] and not DOC_ID_RE.match(r["doc_id"]):
            errors.append(f"{i}행: doc_id 형식 {r['doc_id']!r}")
        if r["effective_date"] and not DATE_RE.match(r["effective_date"]):
            errors.append(f"{i}행: effective_date 형식 {r['effective_date']!r}")
        if r["table_heavy"] and r["table_heavy"] not in ("true", "false"):
            errors.append(f"{i}행: table_heavy는 true/false")
        if r["page_count"] and not r["page_count"].isdigit():
            errors.append(f"{i}행: page_count 숫자 아님")
        if not r["file"].endswith(".pdf"):
            errors.append(f"{i}행: file이 .pdf가 아님")
        if d.doc_id in seen_id:
            errors.append(f"{i}행: doc_id 중복 {d.doc_id}")
        if d.file in seen_file:
            errors.append(f"{i}행: file 중복 {d.file}")
        seen_id.add(d.doc_id)
        seen_file.add(d.file)
    if errors:
        raise ValueError("\n".join(errors))
    return docs


def to_metadata(doc: Doc) -> tuple[dict, list[str]]:
    """원장 한 행 → (메타데이터 파일 내용, 빠진 키 목록). 빈 칸은 키를 넣지 않는다."""
    attrs: dict[str, dict] = {}
    missing: list[str] = []
    r = doc.row
    for key, typ in FIELDS.items():
        raw = r[key]
        if not raw:
            missing.append(key)
            continue
        if typ == "STRING":
            value = {"type": "STRING", "stringValue": raw}
        elif typ == "NUMBER":
            value = {"type": "NUMBER", "numberValue": int(raw)}
        elif typ == "BOOLEAN":
            value = {"type": "BOOLEAN", "booleanValue": raw == "true"}
        else:
            items = [x.strip() for x in raw.split(";") if x.strip()]
            value = {"type": "STRING_LIST", "stringListValue": items}
        attrs[key] = {"value": value, "includeForEmbedding": key in EMBED_KEYS}
    date = r["effective_date"]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        attrs["effective_ymd"] = {
            "value": {"type": "NUMBER", "numberValue": int(date.replace("-", ""))},
            "includeForEmbedding": False,
        }
    return {"metadataAttributes": attrs}, missing


def metadata_name(pdf_name: str) -> str:
    return pdf_name + SUFFIX


def pdf_pages(path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)
