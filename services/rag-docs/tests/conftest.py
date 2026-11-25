"""시험 공통: 가짜 PDF와 작은 원장."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import catalog as cat


def make_pdf(path: Path, pages: int) -> Path:
    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        w.write(f)
    return path


ROWS = [
    {
        "file": "대기환경보전법시행규칙_별표8_배출허용기준_현행_제71호_20261112.pdf",
        "folder": "laws", "doc_id": "air-rule_appx-08", "law_name": "대기환경보전법 시행규칙",
        "title_ko": "별표 8 대기오염물질의 배출허용기준", "doc_type": "별표", "part": "별표8",
        "doc_no": "기후에너지환경부령 제71호", "effective_date": "2026-11-12",
        "amendment_mark": "<개정 2026. 11. 4.>", "effective_status": "현행",
        "authority_class": "시행규칙", "tms_relevance": "직접", "source_org": "기후에너지환경부",
        "related_articles": "시행규칙 제15조; 시행규칙 제33조", "table_heavy": "true",
        "page_count": "3", "caveat": "", "notes_private": "",
    },
    {
        "file": "굴뚝원격감시체계업무편람_본문_2024년12월판.pdf",
        "folder": "handbook", "doc_id": "tms-handbook-2024", "law_name": "굴뚝 원격감시체계 업무편람",
        "title_ko": "굴뚝 원격감시체계 업무편람 2024년 12월판", "doc_type": "편람", "part": "본문",
        "doc_no": "", "effective_date": "2024-12", "amendment_mark": "", "effective_status": "구판",
        "authority_class": "업무편람", "tms_relevance": "직접", "source_org": "한국환경공단",
        "related_articles": "", "table_heavy": "false", "page_count": "2",
        "caveat": "구판. 부과금 숫자 인용 금지", "notes_private": "발간 일자 미확인",
    },
]


def write_catalog(path: Path, rows: list[dict] = ROWS) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cat.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    return write_catalog(tmp_path / "docs_catalog.csv")


@pytest.fixture
def dest(tmp_path: Path) -> Path:
    d = tmp_path / "upload"
    make_pdf(d / "laws" / ROWS[0]["file"], 3)
    make_pdf(d / "handbook" / ROWS[1]["file"], 2)
    return d
