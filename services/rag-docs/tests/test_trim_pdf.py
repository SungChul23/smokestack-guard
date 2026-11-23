from pathlib import Path

import pytest
from conftest import make_pdf

import trim_pdf


def test_trim_keeps_range_and_leaves_source(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    before = src.read_bytes()
    out = tmp_path / "out" / "new.pdf"
    assert trim_pdf.main([str(src), "--pages", "2-3", "--out", str(out)]) == 0
    from pypdf import PdfReader

    assert len(PdfReader(str(out)).pages) == 2
    assert src.read_bytes() == before


@pytest.mark.parametrize("pages", ["0-2", "3-2", "2-9", "x"])
def test_bad_ranges(tmp_path: Path, pages: str):
    src = make_pdf(tmp_path / "src.pdf", 3)
    assert trim_pdf.main([str(src), "--pages", pages, "--out", str(tmp_path / "o.pdf")]) == 2


def test_refuses_to_overwrite_source(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    assert trim_pdf.main([str(src), "--pages", "1-2", "--out", str(src)]) == 2
