import json
from pathlib import Path

import pytest
from conftest import ROWS

import check_metadata as chk
import make_metadata


@pytest.fixture
def ready(catalog_path: Path, dest: Path, tmp_path: Path) -> Path:
    assert make_metadata.main(["--dest", str(dest), "--catalog", str(catalog_path),
                               "--missing", str(tmp_path / "m.csv")]) == 0
    return dest


def meta_of(dest: Path, i: int) -> Path:
    r = ROWS[i]
    return dest / r["folder"] / (r["file"] + ".metadata.json")


def edit(path: Path, fn) -> None:
    body = json.loads(path.read_text("utf-8"))
    fn(body["metadataAttributes"])
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def run(dest: Path, capsys) -> tuple[int, str]:
    code = chk.main(["--dest", str(dest)])
    return code, capsys.readouterr().out


def test_all_pass(ready: Path, capsys):
    code, out = run(ready, capsys)
    assert code == 0 and "통과 2/2" in out


def test_pdf_without_pair(ready: Path, capsys):
    meta_of(ready, 1).unlink()
    code, out = run(ready, capsys)
    assert code == 1 and "짝 없음" in out and "통과 1/2" in out


def test_json_without_pdf(ready: Path, capsys):
    (ready / "laws" / "x.pdf.metadata.json").write_text("{}", encoding="utf-8")
    code, out = run(ready, capsys)
    assert code == 1 and "짝 PDF 없음" in out


def test_wrong_name_and_stray_files(ready: Path, capsys):
    (ready / "laws" / "메모.txt").write_text("x", encoding="utf-8")
    (ready / "laws" / "a.json").write_text("{}", encoding="utf-8")
    (ready / "missing_fields.csv").write_text("x", encoding="utf-8")
    code, out = run(ready, capsys)
    assert code == 1 and out.count("외 파일") == 2 and "폴더(laws/·handbook/) 밖" in out


def test_broken_json(ready: Path, capsys):
    meta_of(ready, 0).write_text("{not json", encoding="utf-8")
    code, out = run(ready, capsys)
    assert code == 1 and "JSON 오류" in out


@pytest.mark.parametrize("change,expect", [
    (lambda a: a.__setitem__("caveat", {"value": {"type": "DATE", "stringValue": "x"},
                                         "includeForEmbedding": False}), "허용되지 않는 타입"),
    (lambda a: a["law_name"]["value"].__setitem__("stringValue", " "), "빈 문자열"),
    (lambda a: a["related_articles"]["value"].__setitem__("stringListValue", []), "빈 목록"),
    (lambda a: a["doc_no"]["value"].__setitem__("stringValue", None), "null 불가"),
    (lambda a: a.pop("effective_status"), "필수 키 없음: effective_status"),
    (lambda a: a["doc_no"].__setitem__("includeForEmbedding", True), "includeForEmbedding는 False"),
    (lambda a: a["page_count"]["value"].__setitem__("numberValue", 55), "page_count 55 ≠ PDF 3쪽"),
])
def test_attribute_errors(ready: Path, capsys, change, expect):
    edit(meta_of(ready, 0), change)
    code, out = run(ready, capsys)
    assert code == 1 and expect in out


def test_size_limit(ready: Path, capsys):
    edit(meta_of(ready, 0), lambda a: a["caveat"].__setitem__("value", {
        "type": "STRING", "stringValue": "가" * 4000}) if "caveat" in a else a.__setitem__(
        "caveat", {"value": {"type": "STRING", "stringValue": "가" * 4000},
                   "includeForEmbedding": False}))
    code, out = run(ready, capsys)
    assert code == 1 and "크기" in out


def test_duplicate_doc_id(ready: Path, capsys):
    edit(meta_of(ready, 1), lambda a: a["doc_id"]["value"].__setitem__("stringValue",
                                                                         ROWS[0]["doc_id"]))
    code, out = run(ready, capsys)
    assert code == 1 and "doc_id 중복" in out
