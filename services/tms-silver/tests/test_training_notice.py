# ruff: noqa: E501  (한글 본문·메일 문구 줄이 길다)
"""학습 스냅샷 알림 (spec 015 US3): 기록 고르기, Silver 짝, 실패·없음, 본문, dry_run."""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import lambda_training_snapshot_notice as n

B = n.BUCKET


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, rec: dict):
        self.objects[key] = json.dumps(rec).encode()

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[Key])}

    def get_paginator(self, _name):
        fake = self

        class P:
            def paginate(self, Bucket, Prefix, StartAfter=""):  # noqa: N803
                keys = sorted(k for k in fake.objects if k.startswith(Prefix) and k > StartAfter)
                yield {"Contents": [{"Key": k} for k in keys]}

        return P()


def _ts(day: str, hhmm: str) -> str:
    """KST 날짜·시각 → UTC ISO (기록은 UTC)."""
    kst = datetime.fromisoformat(f"{day}T{hhmm}:00+09:00")
    return kst.astimezone(UTC).isoformat()


def _key(prefix: str, iso: str, rid: str) -> str:
    return f"{prefix}/{datetime.fromisoformat(iso):%Y%m%dT%H%M%SZ}_{rid}.json"


def add_day(s3, src: str, day: str, silver_sid: int, ml_sid: int, result: str = "passed", hh: str = "03"):
    cfg = n.SOURCES[src]
    m = "00" if src == "ktms" else "30"
    s_start, s_end = _ts(day, f"{hh}:{m}"), _ts(day, f"{hh}:{int(m) + 10:02d}")
    s3.put(_key(cfg["silver_runs"], s_start, f"s{silver_sid}"),
           {"result": "succeeded", "snapshot_id": silver_sid, "started_at": s_start, "finished_at": s_end})
    ml_start = _ts(day, f"{hh}:{int(m) + 12:02d}")
    ml_key = _key(f"silver2/_runs/{cfg['ml_ready'].split('.')[1]}", ml_start, f"m{ml_sid}")
    s3.put(ml_key, {"result": "succeeded", "snapshot_id": ml_sid, "started_at": ml_start,
                    "finished_at": _ts(day, f"{hh}:{int(m) + 20:02d}")})
    c_start = _ts(day, f"{hh}:{int(m) + 22:02d}")
    s3.put(_key(n.CHECK_PREFIX, c_start, f"c{ml_sid}"),
           {"table": cfg["ml_ready"], "result": result, "snapshot_id": ml_sid, "started_at": c_start,
            "ml_ready_run_record": f"s3://{B}/{ml_key}", "range": {"start": day, "end": day}})


NOW = datetime(2026, 11, 22, 5, 0, tzinfo=UTC) - (datetime(2026, 1, 1, 9) - datetime(2026, 1, 1))  # 11-22 05:00 KST


def test_latest_first_with_silver_pair_and_confirmed_range():
    s3 = FakeS3()
    for i, d in enumerate(["2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"]):
        add_day(s3, "ktms", d, 100 + i, 200 + i)
        add_day(s3, "ktms_synth", d, 300 + i, 400 + i)
    out = n.run({"dry_run": True}, s3, publish=None, now=NOW)
    k = out["sources"]["ktms"]
    assert [r["run_date"] for r in k][:3] == ["2026-11-22", "2026-11-21", "2026-11-20"]
    assert (k[0]["silver_snapshot"], k[0]["ml_ready_snapshot"]) == (103, 203)
    assert (k[0]["confirmed_from"], k[0]["confirmed_to"]) == ("2026-10-30", "2026-11-20")
    s = out["sources"]["ktms_synth"][0]
    assert (s["silver_snapshot"], s["ml_ready_snapshot"]) == (303, 403)
    assert out["published"] is False
    body = out["body"]
    assert "[최신] 11-22 실행 · 확정 10-30 ~ 11-20" in body
    assert "FOR VERSION AS OF 203" in body and "FOR VERSION AS OF 403" in body
    assert "TIMESTAMP '2026-11-21 00:00:00'" in body
    assert body.count("  [최신] ") == 2 and "11-19 실행" not in body  # 출처마다 최신 1, 최근 3회만
    assert "학습(Train)에만" in body
    assert out["subject"].startswith("[tms] 학습 스냅샷 2026-11-22")


def test_failed_today_falls_back_to_last_passed():
    s3 = FakeS3()
    add_day(s3, "ktms", "2026-11-21", 1, 11)
    add_day(s3, "ktms", "2026-11-22", 2, 12, result="violation")
    out = n.run({"dry_run": True}, s3, publish=None, now=NOW)
    assert "오늘 새 스냅샷 없음: 검사 violation" in out["body"]
    assert "[최신] 11-21 실행" in out["body"] and "FOR VERSION AS OF 11" in out["body"]
    assert "FOR VERSION AS OF 12" not in out["body"]
    # 합성은 기록이 없다
    assert "오늘 새 스냅샷 없음: 실행 없음" in out["body"]
    assert "최근 7일 통과한 스냅샷 없음" in out["body"]


def test_manual_backfill_pairs_with_silver_finished_before_ml_ready():
    """손으로 다시 계산한 경우: Silver 여러 번 → ML-ready 한 번. 그 직전 Silver를 짝으로."""
    s3 = FakeS3()
    cfg = n.SOURCES["ktms_synth"]
    for sid, hhmm in [(501, "10:00"), (502, "10:20"), (503, "10:40")]:
        st = _ts("2026-11-21", hhmm)
        s3.put(_key(cfg["silver_runs"], st, f"s{sid}"),
               {"result": "succeeded", "snapshot_id": sid, "started_at": st, "finished_at": _ts("2026-11-21", f"10:{int(hhmm[3:]) + 10:02d}")})
    ml_start = _ts("2026-11-21", "10:50")
    ml_key = _key("silver2/_runs/ktms_synth_ml_ready", ml_start, "m9")
    s3.put(ml_key, {"result": "succeeded", "snapshot_id": 9, "started_at": ml_start})
    late = _ts("2026-11-21", "12:00")  # ML-ready 뒤에 끝난 Silver는 짝이 아니다
    s3.put(_key(cfg["silver_runs"], late, "s504"),
           {"result": "succeeded", "snapshot_id": 504, "started_at": late, "finished_at": late})
    c = _ts("2026-11-21", "11:30")
    s3.put(_key(n.CHECK_PREFIX, c, "c9"), {"table": cfg["ml_ready"], "result": "passed", "snapshot_id": 9,
                                          "started_at": c, "ml_ready_run_record": f"s3://{B}/{ml_key}"})
    row = n.run({"dry_run": True, "as_of": "2026-11-21"}, s3, publish=None, now=NOW)["sources"]["ktms_synth"][0]
    assert (row["silver_snapshot"], row["ml_ready_snapshot"]) == (503, 9)


def test_publish_called_once_unless_dry_run():
    s3 = FakeS3()
    add_day(s3, "ktms", "2026-11-22", 1, 2)
    sent = []
    out = n.run({}, s3, publish=lambda s, b: sent.append((s, b)), now=NOW)
    assert out["published"] and len(sent) == 1 and sent[0][0] == out["subject"]


def test_as_of_input_and_no_email_in_code():
    assert n.run({"as_of": "2026-11-20", "dry_run": True}, FakeS3(), publish=None, now=NOW)["subject"].startswith(
        "[tms] 학습 스냅샷 2026-11-20")
    src = Path(n.__file__).read_text(encoding="utf-8")
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", src)
    assert date(2026, 10, 30) == n.SOURCES["ktms_synth"]["first_day"]
