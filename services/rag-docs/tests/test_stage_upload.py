from pathlib import Path

from conftest import ROWS, make_pdf

import catalog as cat
import stage_upload


def test_copies_by_catalog_and_keeps_trimmed(tmp_path: Path, catalog_path: Path):
    src1, src2, dest = tmp_path / "a", tmp_path / "b", tmp_path / "upload"
    make_pdf(src2 / ROWS[1]["file"], 2)
    make_pdf(src1 / "대기환경보전법시행규칙_별표8_배출허용기준_제71호_20261112.pdf", 5)  # 원본 55쪽 역할
    trimmed = make_pdf(dest / "laws" / ROWS[0]["file"], 3)  # trim_pdf 결과가 이미 있음
    copied, extra = stage_upload.stage(cat.read_catalog(catalog_path), [src1, src2], dest)
    assert copied == [f"handbook/{ROWS[1]['file']}"]
    assert extra == [] and trimmed.is_file()
    assert not (dest / "laws" / "대기환경보전법시행규칙_별표8_배출허용기준_제71호_20261112.pdf").exists()


def test_missing_source_is_error(tmp_path: Path, catalog_path: Path, capsys):
    code = stage_upload.main(["--src", str(tmp_path / "none"), "--dest", str(tmp_path / "u"),
                              "--catalog", str(catalog_path)])
    assert code == 2 and "찾지 못함" in capsys.readouterr().err


def test_warns_on_extra_and_prints_sync(tmp_path: Path, catalog_path: Path, capsys):
    src, dest = tmp_path / "s", tmp_path / "u"
    make_pdf(src / ROWS[0]["file"], 3)
    make_pdf(src / ROWS[1]["file"], 2)
    make_pdf(dest / "laws" / "옛문서.pdf", 1)
    code = stage_upload.main(["--src", str(src), "--dest", str(dest), "--catalog", str(catalog_path)])
    out = capsys.readouterr().out
    assert code == 1 and "laws/옛문서.pdf" in out
    assert "aws s3 sync" in out and "--dryrun" in out and '--include "*.md.metadata.json"' in out
