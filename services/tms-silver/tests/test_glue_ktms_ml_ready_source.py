"""ML-ready 잡의 --data_source 인자 (spec 011 T026). Spark·Iceberg 없이 가짜 읽기·쓰기로 확인."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from ktms_cases import build_silver

import glue_ktms_ml_ready
import ktms_pipeline as kp

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=UTC)


@pytest.fixture
def fake_io(monkeypatch):
    written = {}
    monkeypatch.setattr(kp, "build_spark", lambda app: None)
    monkeypatch.setattr(kp, "runtime_versions", lambda spark=None: {"python": "test"})
    monkeypatch.setattr(kp, "read_range", lambda spark, table, col, lo, hi: build_silver())
    monkeypatch.setattr(kp, "ml_ready_schema", lambda: None)
    monkeypatch.setattr(kp, "ensure_table", lambda *a, **k: [])

    def overwrite(spark, df, schema, table, col, r, summary):
        written["df"] = df
        return 123

    monkeypatch.setattr(kp, "overwrite_range", overwrite)
    return written


def _run(tmp_path, *extra):
    argv = ["--start_date", "2026-11-02", "--end_date", "2026-11-03", "--local",
            "--runs_dir", str(tmp_path), "--JOB_RUN_ID", "jr", *extra]  # fmt: skip
    glue_ktms_ml_ready.main(argv, now=NOW)
    rec = sorted((tmp_path / "silver2/_runs/ktms_ml_ready").glob("*.json"))[-1]
    return json.loads(rec.read_text(encoding="utf-8"))


def test_default_data_source_is_automatic_ktms(fake_io, tmp_path):
    rec = _run(tmp_path)
    assert rec["data_source"] == "auto"
    assert set(fake_io["df"]["data_source"]) == {"ktms"}


def test_synthetic_data_source_is_passed_to_rules(fake_io, tmp_path):
    rec = _run(tmp_path, "--data_source", "ktms_synth")
    assert rec["data_source"] == "ktms_synth" and rec["result"] == "succeeded"
    assert set(fake_io["df"]["data_source"]) == {"ktms_synth"}
