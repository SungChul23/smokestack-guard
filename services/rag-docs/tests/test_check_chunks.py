import json

import check_chunks as cc

GOOD = """| | | 1 차 | 2 차 | 3 차 | 4 차 |
|-|-|-|-|-|-|
| 가) 적산전력계 미부착 | | 경 고 | 경 고 | 경 고 | 조업정지 5일 |
| 나) 사업장 안의 일부 굴뚝자동측정기기 미부착 | | 경 고 | 경 고 | 조업정지 10일 | 조업정지 30일 |"""

BAD = """| | 1 차 | 2 차 | 3 차 | 4 차 |
|-|-|-|-|-|
| 가) 적산전력계 미부착 | | 경 고 | 경 고 | 조업정지 5일 |
| 나) 사업장 안의 일부 굴뚝자동측정기기 미부착 | | 경 고 | 경 고 | 조업정지 10일 | 조업정지 30일 |"""

GOLD = {"air-rule_appx-36": [
    {"label": "가)", "cells": ["적산전력계 미부착", "경 고", "경 고", "경 고", "조업정지 5일"]}]}


def src(text: str, parent: str | None = None, doc: str = "air-rule_appx-36") -> dict:
    s = {"doc_id": doc, "bedrock-text": text}
    if parent is not None:
        s["bedrock-metadata"] = json.dumps({"parentText": parent})
    return s


def test_good_table_passes_and_matches_golden():
    r = cc.evaluate([src("child", GOOD)], GOLD)["air-rule_appx-36"]
    assert r.ok and r.table_rows == 2 and r.chunks == 1


def test_bad_table_flags_misaligned_and_golden():
    r = cc.evaluate([src("child", BAD)], GOLD)["air-rule_appx-36"]
    assert not r.ok
    assert len(r.misaligned) == 1 and "나)" in r.misaligned[0]
    assert r.golden_fail == ["가)"]


def test_header_and_doubled_letters():
    r = cc.evaluate([src("법제처 3 국가법령정보센터 대기환경보전법 굴굴뚝뚝 자자동동")], {})["air-rule_appx-36"]
    assert r.header_left == 1 and r.doubled == ["굴굴뚝뚝", "자자동동"]


def test_golden_ignores_spaces_and_blank_cells():
    assert cc.has_row("| 가) 적산전력계  미부착 | | 경고 | 경 고 | 경  고 | 조업정지5일 |",
                      ["적산전력계 미부착", "경 고", "경 고", "경 고", "조업정지 5일"])
    assert not cc.has_row("| 가) 적산전력계 미부착 | 경 고 | 경 고 | 조업정지 5일 |",
                          ["적산전력계 미부착", "경 고", "경 고", "경 고", "조업정지 5일"])


def test_golden_file_is_valid():
    g = cc.load_golden(cc.HERE / "golden_rows.yaml")
    assert "air-rule_appx-36" in g and all(len(r["cells"]) >= 4 for r in g["air-rule_appx-36"])


def test_model_note_is_flagged():
    hits = [{"doc_id": "hb", "bedrock-text": "본문 The image appears to be blank or contains no visible text."}]
    r = cc.evaluate(hits, {})["hb"]
    assert r.model_note == 1 and not r.ok
