"""run_backfill 테스트. boto3 클라이언트는 가짜 객체로 대신하고 AWS를 호출하지 않는다."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from botocore.exceptions import ClientError

import run_backfill as rb

LAST_MODIFIED = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
PREFIX = "bronze/tw_cems/historical/"


def _obj(name: str, size: int = 2_500_000_000) -> rb.RawObject:
    return rb.RawObject(key=f"{PREFIX}{name}", size=size, last_modified=LAST_MODIFIED)


# ---------------------------------------------------------------------------
# 가짜 클라이언트
# ---------------------------------------------------------------------------


class FakeS3:
    def __init__(self, names: list[str], success_months: set[str] | None = None):
        self.names = names
        self.success_keys = {
            f"tw_cems_raw/year={m[:4]}/month={m[5:]}/_SUCCESS" for m in (success_months or set())
        }
        self.head_calls: list[str] = []

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        names = self.names

        class _Paginator:
            def paginate(self, Bucket: str, Prefix: str):  # noqa: N803 (boto3 인자 이름)
                contents = [
                    {"Key": f"{Prefix}{n}", "Size": 1, "LastModified": LAST_MODIFIED} for n in names
                ]
                # 두 페이지로 나눠 페이지 처리를 확인한다.
                half = len(contents) // 2
                yield {"Contents": contents[:half]}
                yield {"Contents": contents[half:]}
                yield {}  # 빈 페이지(Contents 없음)

        return _Paginator()

    def head_object(self, Bucket: str, Key: str):  # noqa: N803
        self.head_calls.append(Key)
        if Key in self.success_keys:
            return {"ContentLength": 0}
        raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")


class FakeGlue:
    """월마다 시도별 상태 순서를 정해 두고, get_job_run을 부를 때마다 하나씩 돌려준다.

    outcomes = {"2025-03": [["RUNNING", "FAILED"], ["SUCCEEDED"]]}
    → 첫 시도는 한 번 RUNNING 뒤 FAILED, 재시도는 바로 SUCCEEDED.
    """

    def __init__(self, outcomes: dict[str, list[list[str]]], dpu_seconds: float | None = 600.0):
        self.outcomes = {m: [list(a) for a in attempts] for m, attempts in outcomes.items()}
        self.dpu_seconds = dpu_seconds
        self.runs: dict[str, dict] = {}
        self.started: list[str] = []
        self.active: set[str] = set()
        self.max_active = 0
        self.crawler_starts: list[str] = []

    def start_job_run(self, JobName: str, Arguments: dict):  # noqa: N803
        month = f"{Arguments['--year']}-{Arguments['--month']}"
        attempt = sum(1 for m in self.started if m == month)
        run_id = f"jr_{len(self.started)}"
        self.started.append(month)
        self.runs[run_id] = {"month": month, "states": self.outcomes[month][attempt]}
        self.active.add(run_id)
        self.max_active = max(self.max_active, len(self.active))
        return {"JobRunId": run_id}

    def get_job_run(self, JobName: str, RunId: str):  # noqa: N803
        run = self.runs[RunId]
        state = run["states"].pop(0) if len(run["states"]) > 1 else run["states"][0]
        if state not in ("RUNNING", "STARTING", "WAITING"):
            self.active.discard(RunId)
        job_run = {
            "Id": RunId,
            "JobRunState": state,
            "ExecutionTime": 300,
            "NumberOfWorkers": 5,
        }
        if self.dpu_seconds is not None:
            job_run["DPUSeconds"] = self.dpu_seconds
        return {"JobRun": job_run}

    def start_crawler(self, Name: str):  # noqa: N803
        self.crawler_starts.append(Name)


def _no_sleep(_seconds: float) -> None:
    pass


# ---------------------------------------------------------------------------
# parse_months
# ---------------------------------------------------------------------------


def test_parse_months_excludes_keys_not_matching_pattern():
    objects = [
        _obj("2025-03.jsonl"),
        _obj("2025-3.jsonl"),
        _obj("readme.txt"),
        _obj("2025-03.jsonl.gz"),
        _obj("2025-13.jsonl"),
    ]
    targets, _missing = rb.parse_months(objects, "2024-11", "2026-10")
    assert [t.month for t in targets] == ["2025-03"]


def test_parse_months_range_includes_bounds_and_sorts():
    objects = [_obj(f"{m}.jsonl") for m in ["2026-10", "2024-10", "2024-11", "2026-11", "2025-06"]]
    targets, _missing = rb.parse_months(objects, "2024-11", "2026-10")
    assert [t.month for t in targets] == ["2024-11", "2025-06", "2026-10"]


def test_parse_months_reports_missing_months_in_range():
    objects = [_obj("2025-01.jsonl"), _obj("2025-03.jsonl")]
    _targets, missing = rb.parse_months(objects, "2025-01", "2025-04")
    assert missing == ["2025-02", "2025-04"]


def test_list_raw_keys_reads_all_pages():
    s3 = FakeS3(["2025-01.jsonl", "2025-02.jsonl", "2025-03.jsonl"])
    objects = rb.list_raw_keys(s3, "raw", "bronze/tw_cems/historical")
    assert [o.key for o in objects] == [f"{PREFIX}2025-0{i}.jsonl" for i in (1, 2, 3)]


def test_list_raw_keys_ignores_keys_in_sub_folders():
    s3 = FakeS3(["old/2025-03.jsonl", "2025-04.jsonl"])
    objects = rb.list_raw_keys(s3, "raw", "bronze/tw_cems/historical/")
    assert [o.key for o in objects] == [f"{PREFIX}2025-04.jsonl"]


# ---------------------------------------------------------------------------
# plan_targets
# ---------------------------------------------------------------------------


def test_plan_targets_only_missing_skips_months_with_success_marker():
    s3 = FakeS3([], success_months={"2025-03"})
    objects = [_obj("2025-03.jsonl"), _obj("2025-04.jsonl")]
    targets, _ = rb.parse_months(objects, "2025-01", "2025-12")

    planned = rb.plan_targets(s3, targets, "eda", "tw_cems_raw", only_missing=True)

    assert {t.month: t.skipped for t in planned} == {"2025-03": True, "2025-04": False}
    assert "tw_cems_raw/year=2025/month=03/_SUCCESS" in s3.head_calls


def test_plan_targets_without_only_missing_does_not_check_markers():
    s3 = FakeS3([], success_months={"2025-03"})
    targets, _ = rb.parse_months([_obj("2025-03.jsonl")], "2025-01", "2025-12")

    planned = rb.plan_targets(s3, targets, "eda", "tw_cems_raw", only_missing=False)

    assert [t.skipped for t in planned] == [False]
    assert s3.head_calls == []


# ---------------------------------------------------------------------------
# 인자
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["0", "7"])
def test_concurrency_out_of_range_exits_with_code_2(value):
    with pytest.raises(SystemExit) as exc:
        rb.main(["--concurrency", value], s3=FakeS3([]), glue=FakeGlue({}))
    assert exc.value.code == 2


@pytest.mark.parametrize("value", ["2025-3", "2025-13", "202503"])
def test_bad_month_option_exits_with_code_2(value):
    with pytest.raises(SystemExit) as exc:
        rb.main(["--from", value], s3=FakeS3([]), glue=FakeGlue({}))
    assert exc.value.code == 2


def test_from_after_to_exits_with_code_2():
    with pytest.raises(SystemExit) as exc:
        rb.main(["--from", "2026-01", "--to", "2025-01"], s3=FakeS3([]), glue=FakeGlue({}))
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_start_jobs(capsys):
    s3 = FakeS3(["2025-03.jsonl", "2025-04.jsonl"])
    glue = FakeGlue({"2025-03": [["SUCCEEDED"]], "2025-04": [["SUCCEEDED"]]})

    code = rb.main(["--dry-run", "--start-crawler"], s3=s3, glue=glue, sleep=_no_sleep)

    assert code == 0
    assert glue.started == []
    assert glue.crawler_starts == []
    out = capsys.readouterr().out
    assert "2025-03" in out and "2025-04" in out
    assert "2024-11" in out  # 범위 안에서 빠진 월도 출력한다


# ---------------------------------------------------------------------------
# run_all: 재시도, 동시 실행 수
# ---------------------------------------------------------------------------


def test_failed_month_is_retried_exactly_once():
    glue = FakeGlue(
        {
            "2025-03": [["RUNNING", "FAILED"], ["SUCCEEDED"]],
            "2025-04": [["ERROR"], ["TIMEOUT"]],
        }
    )

    results = rb.run_all(glue, ["2025-03", "2025-04"], "job", concurrency=2, sleep=_no_sleep)

    by_month = {r.month: r for r in results}
    assert by_month["2025-03"].state == "SUCCEEDED"
    assert by_month["2025-03"].attempts == 2
    assert by_month["2025-04"].state == "TIMEOUT"
    assert by_month["2025-04"].attempts == 2
    assert glue.started.count("2025-04") == 2  # 세 번째 시도는 없다


def test_main_returns_1_and_lists_failures(capsys):
    s3 = FakeS3(["2025-03.jsonl", "2025-04.jsonl"])
    glue = FakeGlue({"2025-03": [["SUCCEEDED"]], "2025-04": [["FAILED"], ["STOPPED"]]})

    code = rb.main(["--from", "2025-03", "--to", "2025-04"], s3=s3, glue=glue, sleep=_no_sleep)

    assert code == 1
    out = capsys.readouterr().out
    assert "실패" in out and "2025-04" in out.split("실패")[-1]


def test_main_returns_0_when_all_succeed_or_skipped():
    s3 = FakeS3(["2025-03.jsonl", "2025-04.jsonl"], success_months={"2025-03"})
    glue = FakeGlue({"2025-04": [["SUCCEEDED"]]})

    code = rb.main(
        ["--from", "2025-03", "--to", "2025-04", "--only-missing"],
        s3=s3,
        glue=glue,
        sleep=_no_sleep,
    )

    assert code == 0
    assert glue.started == ["2025-04"]


@pytest.mark.parametrize("concurrency", [1, 3, 6])
def test_running_months_never_exceed_concurrency(concurrency):
    months = [f"2025-{m:02d}" for m in range(1, 9)]
    outcomes = {m: [["RUNNING", "RUNNING", "SUCCEEDED"]] for m in months}
    # 한 달은 실패 후 재시도해 재시작도 상한 안에 있는지 본다.
    outcomes["2025-02"] = [["RUNNING", "FAILED"], ["RUNNING", "SUCCEEDED"]]
    glue = FakeGlue(outcomes)

    results = rb.run_all(glue, months, "job", concurrency=concurrency, sleep=_no_sleep)

    assert glue.max_active == concurrency
    assert all(r.state == "SUCCEEDED" for r in results)
    assert [r.month for r in results] == months


class RejectingGlue(FakeGlue):
    """start_job_run이 앞에서부터 정해 둔 오류 코드로 거절한다."""

    def __init__(self, outcomes, reject_codes: list[str]):
        super().__init__(outcomes)
        self.reject_codes = list(reject_codes)
        self.rejected = 0

    def start_job_run(self, JobName, Arguments):  # noqa: N803
        if self.reject_codes:
            self.rejected += 1
            code = self.reject_codes.pop(0)
            raise ClientError({"Error": {"Code": code, "Message": "x"}}, "StartJobRun")
        return super().start_job_run(JobName, Arguments)


def test_other_start_failure_counts_as_attempt_and_is_retried():
    glue = RejectingGlue({"2025-03": [["SUCCEEDED"]]}, ["InternalServiceException"])

    results = rb.run_all(glue, ["2025-03"], "job", concurrency=1, sleep=_no_sleep)

    assert results[0].state == "SUCCEEDED"
    assert results[0].attempts == 2


def test_concurrent_runs_rejection_does_not_use_up_retry():
    """동시 실행 상한 거절은 시도로 세지 않는다. 그 뒤 실제 실패가 나도 재시도 기회가 남아 있다."""
    glue = RejectingGlue(
        {"2025-03": [["FAILED"], ["SUCCEEDED"]]},
        ["ConcurrentRunsExceededException"] * 3,
    )

    results = rb.run_all(glue, ["2025-03"], "job", concurrency=1, sleep=_no_sleep)

    assert glue.rejected == 3
    assert results[0].state == "SUCCEEDED"
    assert results[0].attempts == 2  # 거절 3번은 빠지고, 실제 실패 1번 + 재시도 1번


def test_glue_counting_finished_runs_late_does_not_count_as_attempts():
    """Glue가 끝난 실행을 한 번의 확인 주기 동안 더 세는 상황(2026-11-05 실측)을 흉내 낸다."""

    class LaggingGlue(FakeGlue):
        def __init__(self, outcomes, limit):
            super().__init__(outcomes)
            self.limit = limit
            self.lagging: set[str] = set()  # 끝났지만 아직 세는 실행

        def start_job_run(self, JobName, Arguments):  # noqa: N803
            if len(self.active) + len(self.lagging) >= self.limit:
                raise ClientError(
                    {"Error": {"Code": "ConcurrentRunsExceededException", "Message": "x"}},
                    "StartJobRun",
                )
            return super().start_job_run(JobName, Arguments)

        def get_job_run(self, JobName, RunId):  # noqa: N803
            was_active = RunId in self.active
            response = super().get_job_run(JobName, RunId)
            if was_active and RunId not in self.active:
                self.lagging.add(RunId)
            return response

    months = [f"2025-{m:02d}" for m in range(1, 13)]
    glue = LaggingGlue({m: [["RUNNING", "SUCCEEDED"]] for m in months}, limit=6)

    rejected = []

    def start_job_run_counting(JobName, Arguments):  # noqa: N803
        try:
            return LaggingGlue.start_job_run(glue, JobName, Arguments)
        except ClientError:
            rejected.append(Arguments["--month"])
            raise

    glue.start_job_run = start_job_run_counting

    def sleep_until_next_poll(_seconds):
        glue.lagging.clear()  # 다음 확인 주기에는 Glue 집계가 따라잡는다

    results = rb.run_all(glue, months, "job", concurrency=6, sleep=sleep_until_next_poll)

    assert rejected  # 실제로 거절 상황이 재현되어야 의미가 있다
    assert all(r.state == "SUCCEEDED" for r in results)
    assert all(r.attempts == 1 for r in results)
    assert glue.max_active <= 6


def test_endless_rejection_gives_up_without_hanging():
    glue = RejectingGlue(
        {"2025-03": [["SUCCEEDED"]]},
        ["ConcurrentRunsExceededException"] * (rb.MAX_START_REJECTIONS + 5),
    )

    results = rb.run_all(glue, ["2025-03"], "job", concurrency=1, sleep=_no_sleep)

    assert results[0].state == rb.START_FAILED
    assert results[0].attempts == 0
    assert glue.started == []


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


def test_estimate_cost_uses_dpu_seconds_when_present():
    execution_s, dpu_s, est_usd = rb.estimate_cost(
        {"ExecutionTime": 300, "NumberOfWorkers": 5, "DPUSeconds": 3600.0}
    )
    assert (execution_s, dpu_s) == (300, 3600.0)
    assert est_usd == pytest.approx(0.308)


def test_estimate_cost_falls_back_to_execution_time_times_workers():
    _execution_s, dpu_s, est_usd = rb.estimate_cost({"ExecutionTime": 360, "NumberOfWorkers": 5})
    assert dpu_s == 1800
    assert est_usd == pytest.approx(1800 / 3600 * 0.308)


def test_render_table_has_columns_total_and_failures():
    results = [
        rb.MonthResult("2025-03", "SUCCEEDED", 1, "jr_0", 300, 1500.0, 0.1283),
        rb.MonthResult("2025-04", "FAILED", 2, "jr_2", 60, 300.0, 0.0257),
        rb.MonthResult("2025-05", "SKIPPED", 0, None, None, None, None),
    ]
    text = rb.render_table(results)
    header = text.splitlines()[0]
    for col in ["month", "state", "attempts", "run_id", "execution_s", "dpu_s", "est_usd"]:
        assert col in header
    assert "합계" in text
    assert "2025-04" in text.split("실패")[-1]


# ---------------------------------------------------------------------------
# --start-crawler
# ---------------------------------------------------------------------------


def test_start_crawler_not_called_when_any_month_failed(capsys):
    s3 = FakeS3(["2025-03.jsonl"])
    glue = FakeGlue({"2025-03": [["FAILED"], ["FAILED"]]})

    code = rb.main(
        ["--from", "2025-03", "--to", "2025-03", "--start-crawler"],
        s3=s3,
        glue=glue,
        sleep=_no_sleep,
    )

    assert code == 1
    assert glue.crawler_starts == []
    assert "크롤러" in capsys.readouterr().out


def test_start_crawler_called_when_all_succeeded():
    s3 = FakeS3(["2025-03.jsonl"])
    glue = FakeGlue({"2025-03": [["SUCCEEDED"]]})

    code = rb.main(
        ["--from", "2025-03", "--to", "2025-03", "--start-crawler"],
        s3=s3,
        glue=glue,
        sleep=_no_sleep,
    )

    assert code == 0
    assert glue.crawler_starts == ["tms-eda-tw-cems-crawler"]
