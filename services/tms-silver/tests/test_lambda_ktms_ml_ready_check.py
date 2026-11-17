"""계약 검사 Lambda (spec 010 T005~T007, T012, T019, T027). Athena·S3는 가짜로 대신한다."""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from smokestack_guard.silver import ml_ready_check as mc
from smokestack_guard.silver.ml_ready import COLUMNS, to_ml_ready

import lambda_ktms_ml_ready_check as lc
from ktms_pipeline import DayRange, ml_ready_window

R = DayRange(date(2026, 11, 2), date(2026, 11, 3))
NOW = datetime(2026, 11, 4, 18, 30, tzinfo=UTC)  # KST 11-05 03:30 → auto = 11-03~11-04
ROOT = Path(__file__).resolve().parents[3]


def _source(start="2026-11-01 18:00", end="2026-11-04 02:00", stacks=("A|F|1", "B|F|2"), seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    times = pd.date_range(start, end, freq="30min")
    for i, stack in enumerate(stacks):
        for item in ("nox", "sox"):
            ratio = np.clip(60 + np.cumsum(rng.normal(0, 6, len(times))), 5, 140)
            frames.append(
                pd.DataFrame(
                    {
                        "stack_code": stack,
                        "item_code": item,
                        "measured_at": times,
                        "measure_value": ratio * (40 + i) / 100,
                        "standard_value": 40.0 + i,
                        "ratio_pct": ratio,
                    }
                )
            )
    df = pd.concat(frames, ignore_index=True)
    df["ratio_pct"] = df["measure_value"] / df["standard_value"] * 100
    return df.drop(index=[7, 300]).reset_index(drop=True)  # 빈 칸 몇 개


def _table(source=None, data_source="ktms"):
    """잡이 만든 테이블처럼: 전체 이력으로 계산."""
    return to_ml_ready(_source() if source is None else source, data_source=data_source)


def _window(table, r=R):
    lo, hi = ml_ready_window(r)
    return table[(table.measured_at >= lo) & (table.measured_at <= hi)].reset_index(drop=True)


def _texts(items):
    return [v["text"] for v in items]


# ---------------------------------------------------------------------------
# 판정 (US1, SC-001·SC-002)
# ---------------------------------------------------------------------------


def test_valid_window_passes_without_edge_false_positives():
    window = _window(_table())
    assert window.measured_at.min() < R.start_ts  # 여유 구간을 실제로 담고 있다
    assert lc.evaluate(window, R) == []
    # 같은 행을 C의 check()에 그대로 넣으면 가장자리가 불일치로 나온다(이 래퍼가 필요한 이유)
    assert any("재계산" in f for f in mc.check(window))


def test_last_hour_labels_empty_right_after_daily_run_is_not_a_violation():
    # 매일 실행 직후: 다음날 값이 없어 마지막 날 끝 1시간 라벨이 비어 있다(FR-005)
    table = _table(_source(end="2026-11-03 23:30"))
    last = table[table.measured_at >= "2026-11-03 23:00"]
    assert last["label_ratio_60m"].isna().all()
    assert lc.evaluate(_window(table), R) == []


def _tamper(kind):
    t = _window(_table())
    inside = t.index[(t.measured_at >= R.start_ts) & (t.measured_at < R.end_ts)]
    if kind == "missing_column":
        return t.drop(columns=["ratio_slope_3h"]), "format"
    if kind == "mixed_source":
        t.loc[inside[5], "data_source"] = "ktms_synth"
        return t, "format"
    if kind == "duplicate_key":
        return pd.concat([t, t.loc[[inside[3]]]], ignore_index=True), "format"
    if kind == "label":
        i = t.index[t.index.isin(inside) & t["label_ratio_60m"].notna()][10]
        t.loc[i, "label_ratio_60m"] += 1
        return t, "recompute"
    i = t.index[t.index.isin(inside) & t["ratio_lag_60m"].notna()][10]
    t.loc[i, "ratio_lag_60m"] += 1
    return t, "recompute"


@pytest.mark.parametrize(
    "kind", ["missing_column", "mixed_source", "duplicate_key", "label", "feature"]
)
def test_tampered_samples_are_caught(kind):
    t, expected_kind = _tamper(kind)
    found = lc.evaluate(t, R)
    assert found and expected_kind in {v["kind"] for v in found}, found


def test_same_messages_as_c_check_when_window_equals_range():
    # 여유 구간이 없는 같은 행이면 C의 check()와 문구가 같아야 한다(research R5: 비교 규칙 일치)
    full = _table(_source(start="2026-11-02 00:00", end="2026-11-03 23:30"))
    i = full.index[full["label_entry_60m"].notna()][20]
    full.loc[i, "label_entry_60m"] = 1 - full.loc[i, "label_entry_60m"]
    full.loc[full.index[40], "headroom_pct"] += 3
    assert sorted(_texts(lc.evaluate(full, R))) == sorted(mc.check(full))


def test_athena_extension_dtypes_are_normalized():
    t = _window(_table()).convert_dtypes()  # Athena(awswrangler)처럼 boolean·string·Int64
    assert isinstance(t["feature_valid"].dtype, pd.BooleanDtype)
    assert lc.evaluate(t, R) == []


def test_source_and_overlap_checks_for_synthetic():
    t = _window(_table(data_source="ktms"))
    assert any("data_source" in v["text"] for v in lc.evaluate(t, R, expect_source="ktms_synth"))
    found = lc.evaluate(t, R, real_stacks={"A|F|1", "Z"})
    assert [v["kind"] for v in found] == ["overlap"]


# ---------------------------------------------------------------------------
# 알림 문안 (US1, contracts §4)
# ---------------------------------------------------------------------------


def _out(result="violation", n=3, mode="observe"):
    kinds = ["recompute", "format", "rule", "overlap"]
    return {
        "result": result,
        "table": lc.DEFAULT_TABLE,
        "range": {"start": "2026-11-02", "end": "2026-11-03"},
        "snapshot_id": 123,
        "rows": 4567,
        "run_record": "s3://b/silver2/_runs/ktms_ml_ready_check/x.json",
        "mode": mode,
        "sfn_execution": "exec-1",
        "violation_list": [{"kind": kinds[i % 4], "text": f"항목 {i}"} for i in range(n)],
    }


def test_violation_alert_is_readable_and_ordered():
    subject, body = lc.format_alert(_out(n=3), account="111")
    assert subject.isascii() and len(subject) < 100  # SNS 제목 제약
    assert subject.startswith(
        "[tms] K-TMS contract violation - ktms_ml_ready 2026-11-02~2026-11-03"
    )
    lines = [ln for ln in body.splitlines() if ln.startswith("[")]
    assert lines == ["[형식] 항목 1", "[규칙] 항목 2", "[재계산] 항목 0"]
    for part in (
        "4,567행",
        "스냅샷: 123",
        "모드: observe",
        "x.json",
        '"stage": "check"',
        "stateMachine:tms-silver2-ktms",
        "마지막 통과 스냅샷",
        "실행 이름: exec-1",
    ):
        assert part in body, part


def test_long_violation_list_is_cut_to_ten_lines():
    _, body = lc.format_alert(_out(n=25))
    assert len([ln for ln in body.splitlines() if ln.startswith("[")]) == 10
    assert "외 15건" in body


def test_empty_and_passed_alerts():
    subject, body = lc.format_alert(_out(result="empty", n=0) | {"rows": 0})
    assert subject.isascii() and "no rows" in subject and "누락률 리포트" in body
    assert lc.format_alert(_out(result="passed", n=0)) == ("", "")


# ---------------------------------------------------------------------------
# 진입점 (US1·US2)
# ---------------------------------------------------------------------------


class FakeS3:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.puts = []

    def get_paginator(self, _name):
        s3 = self

        class P:
            def paginate(self, Bucket, Prefix, StartAfter=""):  # noqa: N803
                keys = sorted(k for k in s3.objects if k.startswith(Prefix) and k > StartAfter)
                yield {"Contents": [{"Key": k} for k in keys]}

        return P()

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803
        self.puts.append(Key)
        self.objects[Key] = Body


class FakeQuery:
    def __init__(self, window, snapshot=999, stacks=()):
        self.window, self.snapshot, self.stacks, self.sql = window, snapshot, stacks, []

    def __call__(self, sql, database):
        self.sql.append(sql)
        assert database == "tms_silver2"
        assert re.match(r"^\s*SELECT", sql) and ";" not in sql  # 읽기만
        if "$snapshots" in sql:
            return pd.DataFrame({"snapshot_id": [self.snapshot]})
        if "DISTINCT stack_code" in sql:
            return pd.DataFrame({"stack_code": list(self.stacks)})
        return self.window


def _ml_ready_record(job="jr_1", result="succeeded"):
    key = f"{lc.ML_READY_RUNS_PREFIX}/20261104T180500Z_{job}.json"
    rec = {
        "result": result,
        "range": {"start": "2026-11-02", "end": "2026-11-03"},
        "snapshot_id": 42,
    }
    return {key: json.dumps(rec).encode()}


def _event(**args):
    return {
        "args": {"start_date": "auto", "end_date": "auto", "stage": "all", "notify": True, **args},
        "ml_ready_job_run_id": "jr_1",
        "sfn_execution": "exec-1",
        "mode": "observe",
    }


def test_run_uses_ml_ready_record_and_writes_check_record():
    s3, q = FakeS3(_ml_ready_record()), FakeQuery(_window(_table()))
    out = lc.run(_event(), s3, q, "bkt", "req-1", "111", now=NOW)
    assert out["result"] == "passed" and out["subject"] == "" and out["block"] is False
    assert out["range"] == {"start": "2026-11-02", "end": "2026-11-03"} and out["snapshot_id"] == 42
    assert "FOR VERSION AS OF 42" in q.sql[0]
    assert "TIMESTAMP '2026-11-01 21:30:00' AND TIMESTAMP '2026-11-04 00:30:00'" in q.sql[0]
    assert s3.puts == ["silver2/_runs/ktms_ml_ready_check/20261104T183000Z_req-1.json"]
    rec = json.loads(s3.objects[s3.puts[0]])
    assert rec["range_source"] == "ml_ready_run" and rec["ml_ready_run_record"].endswith(
        "_jr_1.json"
    )
    assert rec["result"] == "passed" and rec["rows"] > 0 and rec["window_rows"] > rec["rows"]


def test_stage_check_uses_input_range_and_latest_snapshot():
    q = FakeQuery(_window(_table()), snapshot=7)
    event = _event(stage="check", start_date="2026-11-02", end_date="2026-11-03") | {
        "ml_ready_job_run_id": None
    }
    out = lc.run(event, FakeS3(), q, "bkt", "req-2", "111", now=NOW)
    assert out["snapshot_id"] == 7 and out["result"] == "passed"
    assert "$snapshots" in q.sql[0]


def test_violation_in_block_mode_sets_block():
    t, _ = _tamper("label")
    event = _event() | {"mode": "block"}
    out = lc.run(event, FakeS3(_ml_ready_record()), FakeQuery(t), "bkt", "r", "111", now=NOW)
    assert out["result"] == "violation" and out["block"] is True
    assert "violation_list" not in out and out["subject"].startswith(
        "[tms] K-TMS contract violation"
    )


def test_empty_range():
    empty = _window(_table()).iloc[0:0]
    out = lc.run(_event(), FakeS3(_ml_ready_record()), FakeQuery(empty), "bkt", "r", "111", now=NOW)
    assert out["result"] == "empty" and out["block"] is False and "no rows" in out["subject"]


def test_failure_is_recorded_then_raised():
    s3 = FakeS3(_ml_ready_record(result="failed"))
    with pytest.raises(ValueError, match="성공이 아니다"):
        lc.run(_event(), s3, FakeQuery(None), "bkt", "r", "111", now=NOW)
    rec = json.loads(s3.objects[s3.puts[0]])
    assert rec["result"] == "failed" and "성공이 아니다" in rec["error"]


def test_missing_ml_ready_record_fails():
    with pytest.raises(LookupError):
        lc.run(_event(), FakeS3(), FakeQuery(None), "bkt", "r", "111", now=NOW)


def test_real_table_overlap_through_run():
    q = FakeQuery(_window(_table(data_source="ktms_synth")), stacks=["A|F|1"])
    event = _event(expect_source="ktms_synth", real_table="tms_silver2.ktms")
    out = lc.run(event, FakeS3(_ml_ready_record()), q, "bkt", "r", "111", now=NOW)
    assert out["result"] == "violation" and "[겹침]" in out["message"]


# ---------------------------------------------------------------------------
# 입력·권한 (US2)
# ---------------------------------------------------------------------------


def test_parse_event_defaults_and_validation():
    p = lc.parse_event({"args": {}})
    assert (p["stage"], p["notify"], p["check_table"], p["mode"]) == (
        "all",
        True,
        lc.DEFAULT_TABLE,
        "observe",
    )
    assert lc.parse_event({"args": {"notify": "false"}})["notify"] is False
    for bad in (
        {"mode": "off"},
        {"args": {"stage": "train"}},
        {"args": {"check_table": "x"}},
        {"args": {"notify": "maybe"}},
    ):
        with pytest.raises(ValueError):
            lc.parse_event(bad)


def test_lambda_policy_cannot_write_tables():
    tf = (ROOT / "infra/stacks/tms-silver/ktms_check.tf").read_text(encoding="utf-8")
    puts = re.findall(
        r'actions\s*=\s*\[[^\]]*"s3:(?:PutObject|DeleteObject)"[^\]]*\]\s*resources\s*=\s*\[([^\]]*)\]',
        tf,
    )
    assert puts, "쓰기 권한 문장을 찾지 못했다"
    for resources in puts:
        assert "ktms_check_runs" in resources or "athena-results" in resources, resources
    assert 'ktms_check_runs = "silver2/_runs/ktms_ml_ready_check"' in tf
    assert "DeleteObject" not in tf
    assert "sns:Publish" not in tf  # 알림은 상태 머신이 보낸다


def test_columns_constant_matches_contract():
    assert len(COLUMNS) == 36


def test_synthetic_check_reads_its_own_ml_ready_record():
    """011: 합성 검사는 silver2/_runs/ktms_synth_ml_ready/ 기록에서 범위·스냅샷을 찾는다."""
    assert lc.runs_prefix(lc.DEFAULT_TABLE) == lc.ML_READY_RUNS_PREFIX
    key = "silver2/_runs/ktms_synth_ml_ready/20261104T180500Z_jr_s.json"
    rec = {
        "result": "succeeded",
        "range": {"start": "2026-11-02", "end": "2026-11-03"},
        "snapshot_id": 77,
    }
    s3 = FakeS3({key: json.dumps(rec).encode()})
    q = FakeQuery(_window(_table(data_source="ktms_synth")), stacks=["Z"])
    event = _event(
        check_table="tms_silver2.ktms_synth_ml_ready",
        expect_source="ktms_synth",
        real_table="tms_silver2.ktms_ml_ready",
    ) | {"ml_ready_job_run_id": "jr_s"}
    out = lc.run(event, s3, q, "bkt", "r", "111", now=NOW)
    assert out["result"] == "passed" and out["snapshot_id"] == 77
    assert '"tms_silver2"."ktms_synth_ml_ready" FOR VERSION AS OF 77' in q.sql[0]
