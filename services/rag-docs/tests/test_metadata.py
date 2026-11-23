import csv
import json
from pathlib import Path

import pytest
from conftest import ROWS, write_catalog

import catalog as cat
import make_metadata


def test_types_embedding_flags_and_missing(catalog_path: Path, dest: Path, tmp_path: Path):
    before = (dest / "laws" / ROWS[0]["file"]).read_bytes()
    missing = tmp_path / "missing.csv"
    assert make_metadata.main(["--dest", str(dest), "--catalog", str(catalog_path),
                               "--missing", str(missing)]) == 0
    law = json.loads((dest / "laws" / (ROWS[0]["file"] + ".metadata.json")).read_text("utf-8"))
    a = law["metadataAttributes"]
    assert a["law_name"] == {"value": {"type": "STRING", "stringValue": "대기환경보전법 시행규칙"},
                             "includeForEmbedding": True}
    assert {k for k, v in a.items() if v["includeForEmbedding"]} == {"law_name", "title_ko", "part"}
    assert a["related_articles"]["value"] == {"type": "STRING_LIST",
                                              "stringListValue": ["시행규칙 제15조", "시행규칙 제33조"]}
    assert a["table_heavy"]["value"] == {"type": "BOOLEAN", "booleanValue": True}
    assert a["page_count"]["value"] == {"type": "NUMBER", "numberValue": 3}
    assert a["effective_ymd"]["value"]["numberValue"] == 20261112
    assert "caveat" not in a and "notes_private" not in a
    assert (dest / "laws" / ROWS[0]["file"]).read_bytes() == before

    hb = json.loads((dest / "handbook" / (ROWS[1]["file"] + ".metadata.json")).read_text("utf-8"))
    h = hb["metadataAttributes"]
    assert "doc_no" not in h and "related_articles" not in h  # 빈 칸 = 키 생략
    assert "effective_ymd" not in h  # 2024-12: 일 없음 → 숫자 날짜 없음
    assert h["effective_status"]["value"]["stringValue"] == "구판"
    rows = list(csv.reader(missing.open(encoding="utf-8")))
    assert ["tms-handbook-2024", "doc_no"] in rows and ["tms-handbook-2024", "related_articles"] in rows
    assert not any(r[1] in ("caveat", "amendment_mark") for r in rows[1:])  # 선택 키는 빠진 목록에 없음


def test_pdf_not_in_catalog_is_error(catalog_path: Path, dest: Path, tmp_path: Path):
    (dest / "laws" / "모르는문서.pdf").write_bytes(b"%PDF-1.4")
    assert make_metadata.main(["--dest", str(dest), "--catalog", str(catalog_path),
                               "--missing", str(tmp_path / "m.csv")]) == 2


@pytest.mark.parametrize("col,val", [
    ("effective_status", "최신"), ("folder", "etc"), ("doc_id", "Air Rule"),
    ("effective_date", "2026.11.12"), ("table_heavy", "yes"), ("law_name", ""),
])
def test_catalog_rejects_bad_values(tmp_path: Path, col: str, val: str):
    rows = [dict(ROWS[0]), dict(ROWS[1])]
    rows[0][col] = val
    with pytest.raises(ValueError):
        cat.read_catalog(write_catalog(tmp_path / "c.csv", rows))


def test_catalog_rejects_duplicate_doc_id(tmp_path: Path):
    rows = [dict(ROWS[0]), dict(ROWS[1])]
    rows[1]["doc_id"] = rows[0]["doc_id"]
    with pytest.raises(ValueError, match="중복"):
        cat.read_catalog(write_catalog(tmp_path / "c.csv", rows))
