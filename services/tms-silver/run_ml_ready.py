"""TW CEMS ML-ready Glue Job을 1회 실행하고 결과를 출력한다 (사람이 실행하는 명령).

- --mode build: ML-ready를 만든다. 끝나면 latest.json의 건수를 출력한다.
- --mode compare: C의 pandas 결과와 비교한다. 끝나면 passed와 불일치 컬럼을 출력한다.
- 자동 재시도는 하지 않는다. 1회 실행이고 전체 덮어쓰기라 사람이 판단한다.

자격증명은 실행자의 환경 변수나 `--profile`에서 읽는다. 코드에 쓰지 않는다.
계약: specs/a-platform/005-tw-cems-ml-ready-spark/contracts/run-interface.md §2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable

from botocore.exceptions import ClientError

from run_silver import (
    DEFAULT_REGION,
    FAILED_STATES,
    POLL_SECONDS,
    SUCCEEDED,
    _log,
    estimate_cost,
)

DEFAULT_JOB_NAME = "tms-silver-tw-cems-ml-ready"
DEFAULT_BUCKET = "smokestack-tms-raw-952900391026"
DEFAULT_RUNS_PREFIX = "silver/_runs/tw_cems_ml_ready"
BUILD_KEYS = [
    "silver_rows", "selected_rows", "duplicate_keys", "output_rows", "feature_valid_rows",
    "classification_eligible_rows", "regression_eligible_rows", "positive_rows",
    "eligible_positive_rows", "files",
]  # fmt: skip


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["build", "compare"], default="build")
    parser.add_argument("--files", type=int, default=None, help="출력 파일 수 (기본: Job 설정 6)")
    parser.add_argument("--job-name", default=DEFAULT_JOB_NAME)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--runs-prefix", default=DEFAULT_RUNS_PREFIX)
    parser.add_argument("--profile", default=None, help="AWS 프로필 이름")
    parser.add_argument("--region", default=DEFAULT_REGION)
    args = parser.parse_args(argv)
    if args.files is not None and not 1 <= args.files <= 32:
        parser.error(f"--files는 1~32이어야 한다: {args.files}")
    return args


def _read_json(s3, bucket: str, key: str) -> dict | None:
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except (ClientError, ValueError, KeyError):
        return None


def _latest_compare_key(s3, bucket: str, runs_prefix: str) -> str | None:
    prefix = f"{runs_prefix.strip('/')}/compare/"
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys += [item["Key"] for item in page.get("Contents", [])]
    return max(keys) if keys else None  # run_ts(YYYYMMDDTHHMMSSZ) 순서 = 이름 순서


def wait(glue, job_name: str, run_id: str, sleep: Callable[[float], None]) -> dict:
    while True:
        job_run = glue.get_job_run(JobName=job_name, RunId=run_id)["JobRun"]
        state = job_run["JobRunState"]
        if state == SUCCEEDED or state in FAILED_STATES:
            return job_run
        _log(f"{state}")
        sleep(POLL_SECONDS)


def main(
    argv: list[str] | None = None,
    *,
    s3=None,
    glue=None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    args = parse_args(argv)
    if s3 is None or glue is None:
        import boto3

        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        s3 = s3 or session.client("s3")
        glue = glue or session.client("glue")

    arguments = {"--mode": args.mode}
    if args.files is not None:
        arguments["--files"] = str(args.files)
    run_id = glue.start_job_run(JobName=args.job_name, Arguments=arguments)["JobRunId"]
    _log(f"{args.mode} 시작: {run_id}")

    job_run = wait(glue, args.job_name, run_id, sleep)
    state = job_run["JobRunState"]
    execution_s, dpu_s, est_usd = estimate_cost(job_run)
    print(f"state={state} execution_s={execution_s} dpu_s={dpu_s} est_usd={est_usd}", flush=True)
    if state != SUCCEEDED:
        print(f"실패: {job_run.get('ErrorMessage', '-')}", flush=True)
        return 1

    if args.mode == "build":
        record = _read_json(s3, args.bucket, f"{args.runs_prefix.strip('/')}/latest.json")
        if record is None:
            print("latest.json을 읽지 못했다", flush=True)
            return 1
        for key in BUILD_KEYS:
            print(f"{key:30} {record.get(key)}", flush=True)
        return 0

    key = _latest_compare_key(s3, args.bucket, args.runs_prefix)
    record = _read_json(s3, args.bucket, key) if key else None
    if record is None:
        print("compare 기록을 읽지 못했다", flush=True)
        return 1
    print(f"passed={record.get('passed')} ours_rows={record.get('ours_rows')} "
          f"theirs_rows={record.get('theirs_rows')} only_ours={record.get('only_ours')} "
          f"only_theirs={record.get('only_theirs')}", flush=True)  # fmt: skip
    for column, count in (record.get("column_mismatches") or {}).items():
        if count:
            print(f"  불일치 {column}: {count}", flush=True)
    for column, diff in (record.get("max_abs_diff") or {}).items():
        print(f"  최대 차이 {column}: {diff:.3g}", flush=True)
    return 0 if record.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
