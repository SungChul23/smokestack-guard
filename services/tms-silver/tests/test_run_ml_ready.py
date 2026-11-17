"""run_ml_ready 테스트. boto3 클라이언트는 가짜 객체로 대신하고 AWS를 호출하지 않는다."""

from __future__ import annotations

import io
import json

import pytest
from botocore.exceptions import ClientError

import run_ml_ready as rm

RUNS = "silver/_runs/tw_cems_ml_ready"


class FakeS3:
    def __init__(self, objects: dict[str, dict]):
        self.objects = objects

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        return {"Body": io.BytesIO(json.dumps(self.objects[Key]).encode())}

    def get_paginator(self, name):
        objects = self.objects

        class _P:
            def paginate(self, Bucket, Prefix):  # noqa: N803
                yield {"Contents": [{"Key": k} for k in objects if k.startswith(Prefix)]}

        return _P()


class FakeGlue:
    def __init__(self, states: list[str]):
        self.states = list(states)
        self.started: list[dict] = []

    def start_job_run(self, JobName, Arguments):  # noqa: N803
        self.started.append({"JobName": JobName, "Arguments": Arguments})
        return {"JobRunId": "jr_1"}

    def get_job_run(self, JobName, RunId):  # noqa: N803
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        run = {"JobRunState": state, "ExecutionTime": 300, "NumberOfWorkers": 10}
        if state == "FAILED":
            run["ErrorMessage"] = "boom"
        return {"JobRun": run}


def _no_sleep(_s):
    pass


def test_build_success_prints_counts(capsys):
    latest = {"output_rows": 17690000, "eligible_positive_rows": 135978}
    s3 = FakeS3({f"{RUNS}/latest.json": latest})
    glue = FakeGlue(["RUNNING", "SUCCEEDED"])

    assert rm.main(["--mode", "build"], s3=s3, glue=glue, sleep=_no_sleep) == 0
    out = capsys.readouterr().out
    assert "17690000" in out and "135978" in out
    assert glue.started == [
        {"JobName": "tms-silver-tw-cems-ml-ready", "Arguments": {"--mode": "build"}}
    ]


def test_compare_failed_returns_1_and_lists_columns(capsys):
    s3 = FakeS3(
        {
            f"{RUNS}/compare/20261109T010000Z.json": {"passed": True, "column_mismatches": {}},
            f"{RUNS}/compare/20261109T020000Z.json": {
                "passed": False,
                "column_mismatches": {"ratio_rolling_std_3h": 3, "ratio_pct": 0},
                "max_abs_diff": {"ratio_rolling_std_3h": 2.5e-5},
            },
        }
    )
    glue = FakeGlue(["SUCCEEDED"])

    assert rm.main(["--mode", "compare"], s3=s3, glue=glue, sleep=_no_sleep) == 1
    out = capsys.readouterr().out
    assert "ratio_rolling_std_3h: 3" in out
    assert "최대 차이 ratio_rolling_std_3h: 2.5e-05" in out
    assert "ratio_pct" not in out.split("passed")[-1]


def test_job_failed_returns_1(capsys):
    glue = FakeGlue(["RUNNING", "FAILED"])
    assert rm.main(["--mode", "build"], s3=FakeS3({}), glue=glue, sleep=_no_sleep) == 1
    assert "boom" in capsys.readouterr().out
    assert len(glue.started) == 1  # 자동 재시도 없음


def test_build_without_latest_returns_1():
    glue = FakeGlue(["SUCCEEDED"])
    assert rm.main(["--mode", "build"], s3=FakeS3({}), glue=glue, sleep=_no_sleep) == 1


def test_files_argument_is_passed():
    glue = FakeGlue(["SUCCEEDED"])
    s3 = FakeS3({f"{RUNS}/latest.json": {}})
    rm.main(["--mode", "build", "--files", "8"], s3=s3, glue=glue, sleep=_no_sleep)
    assert glue.started[0]["Arguments"] == {"--mode": "build", "--files": "8"}


@pytest.mark.parametrize("argv", [["--mode", "bad"], ["--files", "0"], ["--files", "40"]])
def test_bad_arguments_exit_2(argv):
    with pytest.raises(SystemExit) as exc:
        rm.main(argv, s3=FakeS3({}), glue=FakeGlue(["SUCCEEDED"]))
    assert exc.value.code == 2
