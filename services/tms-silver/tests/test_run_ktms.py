"""run_ktms.py (T026). spec 008 US2·US4, research R7."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

import run_ktms
from run_ktms import Step, execution_name, plan_backfill


class FakeSfn:
    def __init__(self, results: list[str]):
        self.results = list(results)
        self.started: list[dict] = []
        self.polls = 0

    def start_execution(self, stateMachineArn, name, input):  # noqa: A002, N803 (boto3 인자 이름)
        self.started.append({"arn": stateMachineArn, "name": name, "input": json.loads(input)})
        return {"executionArn": f"exec-{len(self.started)}"}

    def describe_execution(self, executionArn):  # noqa: N803
        self.polls += 1
        if self.polls % 2:  # 한 번은 진행 중, 다음 번에 결과
            return {"status": "RUNNING"}
        return {"status": self.results[len(self.started) - 1]}


class FakeSession:
    def __init__(self, sfn=None, s3=None):
        self.sfn, self.s3 = sfn, s3

    def client(self, name):
        return {"stepfunctions": self.sfn, "s3": self.s3}[name]


NOW = lambda: datetime(2026, 11, 13, 1, 2, 3, tzinfo=UTC)  # noqa: E731


def test_plan_backfill_silver_chunks_then_one_ml_ready():
    assert plan_backfill(date(2026, 10, 30), date(2026, 11, 12), 5) == [
        Step("silver", date(2026, 10, 30), date(2026, 11, 3)),
        Step("silver", date(2026, 11, 4), date(2026, 11, 8)),
        Step("silver", date(2026, 11, 9), date(2026, 11, 12)),
        Step("ml_ready", date(2026, 10, 30), date(2026, 11, 12)),
    ]


def test_plan_backfill_rejects_bad_chunks():
    with pytest.raises(ValueError, match="1~7"):
        plan_backfill(date(2026, 11, 1), date(2026, 11, 2), 8)
    with pytest.raises(ValueError, match="늦다"):
        plan_backfill(date(2026, 11, 2), date(2026, 11, 1))


def test_execution_name_is_valid():
    name = execution_name(Step("ml_ready", date(2026, 10, 30), date(2026, 11, 12)), NOW())
    assert name == "ktms-mlready-20261030-20261112-20261113T010203"


def test_backfill_runs_in_order(capsys):
    sfn = FakeSfn(["SUCCEEDED"] * 4)
    code = run_ktms.main(
        ["backfill", "--from", "2026-10-30", "--to", "2026-11-12"],
        session=FakeSession(sfn),
        sleep=lambda s: None,
        now=NOW,
    )
    assert code == 0
    assert [s["input"]["stage"] for s in sfn.started] == ["silver", "silver", "silver", "ml_ready"]
    assert sfn.started[-1]["input"] == {
        "start_date": "2026-10-30",
        "end_date": "2026-11-12",
        "stage": "ml_ready",
    }
    assert sfn.started[0]["arn"].endswith(":stateMachine:tms-silver2-ktms")


def test_backfill_stops_on_failure():
    sfn = FakeSfn(["SUCCEEDED", "FAILED", "SUCCEEDED", "SUCCEEDED"])
    code = run_ktms.main(
        ["backfill", "--from", "2026-10-30", "--to", "2026-11-12"],
        session=FakeSession(sfn),
        sleep=lambda s: None,
        now=NOW,
    )
    assert code == 1
    assert len(sfn.started) == 2  # 실패한 뒤 다음 묶음과 ML-ready를 시작하지 않는다


def test_dry_run_calls_nothing(capsys):
    code = run_ktms.main(
        ["backfill", "--from", "2026-10-30", "--to", "2026-11-12", "--dry-run"],
        session=FakeSession(sfn=None),
        now=NOW,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "[4/4] ml_ready" in out and "dry-run" in out


def test_rerun_passes_input():
    sfn = FakeSfn(["SUCCEEDED"])
    code = run_ktms.main(
        ["rerun", "--from", "2026-11-05", "--to", "2026-11-07", "--stage", "ml_ready"],
        session=FakeSession(sfn),
        sleep=lambda s: None,
        now=NOW,
    )
    assert code == 0
    assert sfn.started[0]["input"] == {
        "start_date": "2026-11-05",
        "end_date": "2026-11-07",
        "stage": "ml_ready",
    }


def test_rerun_silver_over_seven_days_is_refused():
    with pytest.raises(SystemExit, match="7일"):
        run_ktms.main(
            ["rerun", "--from", "2026-11-01", "--to", "2026-11-08"], session=FakeSession(), now=NOW
        )


def test_runs_table(fake_s3, capsys):
    for i, result in enumerate(["succeeded", "failed"]):
        rec = {
            "result": result,
            "range": {"start": "2026-11-11", "end": "2026-11-12"},
            "rows": 10 + i,
            "snapshot_id": 123 if result == "succeeded" else None,
            "started_at": f"2026-11-12T18:0{i}:00+00:00",
            "error": None if result == "succeeded" else "ValueError: no snapshots",
        }
        fake_s3.put_object(
            Bucket=run_ktms.DEFAULT_BUCKET,
            Key=f"silver2/_runs/ktms/2026111218000{i}Z_jr.json",
            Body=json.dumps(rec).encode(),
        )
    assert (
        run_ktms.main(["runs", "--table", "ktms", "--last", "5"], session=FakeSession(s3=fake_s3))
        == 0
    )
    out = capsys.readouterr().out
    assert "succeeded" in out and "failed" in out and "ValueError: no snapshots" in out
