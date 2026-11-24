import json
from pathlib import Path

from conftest import ROWS, make_pdf, write_catalog

import catalog as cat
import check_chunks as cc
import check_metadata as chk
import make_metadata
import pdf_to_md as p2m

GOOD = "| 위반 | 1차 | 2차 |\n|-|-|-|\n| 가) | 경 고 | 조업정지 5일 |"
BAD = "| 위반 | 1차 | 2차 |\n|-|-|-|\n| 가) | 경 고 |"


class FakeClient:
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.calls = 0

    def converse(self, **kw):
        self.calls += 1
        assert kw["messages"][0]["content"][0]["image"]["format"] == "png"
        text = self.answers.pop(0) if self.answers else GOOD
        return {"output": {"message": {"content": [{"text": text}]}},
                "usage": {"inputTokens": 2000, "outputTokens": 1000}}


def test_page_problems():
    assert p2m.page_problems(GOOD) == []
    probs = p2m.page_problems(BAD + "\n법제처 1 국가법령정보센터 굴굴뚝뚝")
    assert any(x.startswith("칸:") for x in probs) and "머리글 잔존" in probs
    assert any("굴굴뚝뚝" in x for x in probs)


def test_retry_until_clean_and_keep_best():
    c = FakeClient([BAD, GOOD])
    r = p2m.convert_page(c, "m", "prompt", b"png", tries=3)
    assert r.text == GOOD and r.problems == [] and r.tries == 2 and c.calls == 2
    assert r.tokens_in == 4000 and r.tokens_out == 2000
    c = FakeClient([BAD, BAD, BAD])
    r = p2m.convert_page(c, "m", "prompt", b"png", tries=3)
    assert r.problems and r.tries == 3


def test_convert_doc_caches_and_assembles(tmp_path: Path):
    src = tmp_path / "src"
    make_pdf(src / "laws" / ROWS[0]["file"], 3)
    doc = cat.read_catalog(write_catalog(tmp_path / "c.csv"))[0]
    c = FakeClient([])
    recs = p2m.convert_doc(doc, src, tmp_path / "cache", c, "m", "p", 2, 2, redo=False, log=lambda *_: None)
    assert [r["page"] for r in recs] == [1, 2, 3] and c.calls == 3
    again = p2m.convert_doc(doc, src, tmp_path / "cache", c, "m", "p", 2, 2, redo=False, log=lambda *_: None)
    assert c.calls == 3 and again == recs  # 캐시 재사용
    md = p2m.assemble(recs)
    assert md.count("<!-- 쪽 ") == 3 and md.index("<!-- 쪽 1 -->") < md.index("<!-- 쪽 3 -->")


def test_md_metadata_and_checks(tmp_path: Path, catalog_path: Path, capsys):
    dest = tmp_path / "md"
    for r in ROWS:
        out = dest / r["folder"] / cat.md_name(r["file"])
        out.parent.mkdir(parents=True, exist_ok=True)
        n = int(r["page_count"])
        out.write_text(p2m.assemble([{"page": i, "text": GOOD} for i in range(1, n + 1)]), encoding="utf-8")
    assert make_metadata.main(["--dest", str(dest), "--catalog", str(catalog_path), "--format", "md",
                               "--missing", str(tmp_path / "m.csv")]) == 0
    meta = json.loads((dest / "laws" / (cat.md_name(ROWS[0]["file"]) + ".metadata.json")).read_text("utf-8"))
    assert meta["metadataAttributes"]["source_pdf"]["value"]["stringValue"] == ROWS[0]["file"]
    assert chk.main(["--dest", str(dest)]) == 0 and "통과 2/2" in capsys.readouterr().out
    reports = cc.evaluate(cc.local_hits(dest), {})
    assert set(reports) == {ROWS[0]["doc_id"], ROWS[1]["doc_id"]} and all(r.ok for r in reports.values())
