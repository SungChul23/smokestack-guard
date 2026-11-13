"""K-TMS Silver·ML-ready 상태 머신을 사람이 실행하는 명령 (008). contracts/run-interface.md §4.

    python run_ktms.py backfill --from 2026-10-30 --to 2026-11-12 [--chunk-days 5] [--dry-run]
    python run_ktms.py rerun --from 2026-11-05 --to 2026-11-07 [--stage all|silver|ml_ready]
    python run_ktms.py runs --table ktms [--last 5]

- backfill: Silver를 날짜 묶음별로 차례로 만든 뒤 ML-ready를 전체 범위로 한 번 만든다(research R7).
  묶음마다 ML-ready를 돌리면 묶음 경계의 라벨이 다음 묶음 Silver 없이 계산돼 비기 때문이다.
- 실행은 하나씩 시작하고 30초마다 상태를 본다. 하나가 실패하면 멈추고 종료 코드 1을 돌려준다.
- 자격증명은 실행자의 환경 변수나 `--profile`에서 읽는다. 코드에 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

DEFAULT_REGION = "ap-northeast-2"
DEFAULT_ACCOUNT = "952900391026"
DEFAULT_STATE_MACHINE = "tms-silver2-ktms"
DEFAULT_BUCKET = "smokestack-tms-raw-952900391026"
RUNS_PREFIX = {"ktms": "silver2/_runs/ktms", "ktms_ml_ready": "silver2/_runs/ktms_ml_ready"}
STAGES = ("all", "silver", "ml_ready")
POLL_SECONDS = 30
DONE = {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}


@dataclass(frozen=True)
class Step:
    stage: str
    start: date
    end: date

    def input(self) -> dict[str, str]:
        return {
            "start_date": self.start.isoformat(),
            "end_date": self.end.isoformat(),
            "stage": self.stage,
        }

    def label(self) -> str:
        return f"{self.stage:<8} {self.start} ~ {self.end}"


def plan_backfill(start: date, end: date, chunk_days: int = 5) -> list[Step]:
    if start > end:
        raise ValueError(f"--from({start})가 --to({end})보다 늦다")
    if chunk_days < 1 or chunk_days > 7:
        raise ValueError("--chunk-days는 1~7이어야 한다 (Silver 잡의 max_days 7)")
    steps, cur = [], start
    while cur <= end:
        last = min(cur + timedelta(days=chunk_days - 1), end)
        steps.append(Step("silver", cur, last))
        cur = last + timedelta(days=1)
    steps.append(Step("ml_ready", start, end))
    return steps


def execution_name(step: Step, now: datetime) -> str:
    """Step Functions 실행 이름: 80자 이하, 영숫자·-·_만."""
    stage = step.stage.replace("_", "")
    name = f"ktms-{stage}-{step.start:%Y%m%d}-{step.end:%Y%m%d}-{now:%Y%m%dT%H%M%S}"
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name), name
    return name


def run_step(
    sfn,
    arn: str,
    step: Step,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    name = execution_name(step, now())
    started = time.monotonic()
    resp = sfn.start_execution(stateMachineArn=arn, name=name, input=json.dumps(step.input()))
    print(f"시작  {step.label()}  {name}", flush=True)
    while True:
        status = sfn.describe_execution(executionArn=resp["executionArn"])["status"]
        if status in DONE:
            print(f"{status:<9} {step.label()}  {round(time.monotonic() - started)}s", flush=True)
            return status
        sleep(POLL_SECONDS)


def run_steps(sfn, arn: str, steps: list[Step], dry_run: bool, sleep=time.sleep, now=None) -> int:
    for i, step in enumerate(steps, 1):
        print(f"[{i}/{len(steps)}] {step.label()}  input={json.dumps(step.input())}")
    if dry_run:
        print("dry-run: 실행하지 않았다")
        return 0
    for step in steps:
        status = run_step(sfn, arn, step, sleep=sleep, now=now or (lambda: datetime.now(UTC)))
        if status != "SUCCEEDED":
            print(
                f"멈춤: {step.label()} {status}. 실행 기록: python run_ktms.py runs",
                file=sys.stderr,
            )
            return 1
    return 0


def list_runs(s3, bucket: str, table: str, last: int) -> list[dict]:
    prefix = RUNS_PREFIX[table] + "/"
    keys = [
        o["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        for o in page.get("Contents", [])
        if o["Key"].endswith(".json")
    ]
    out = []
    for key in sorted(keys)[-last:]:
        rec = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
        out.append(rec | {"_key": key})
    return out


def print_runs(records: list[dict]) -> None:
    print(f"{'시작(UTC)':<26} {'결과':<10} {'범위':<24} {'행':>10} {'snapshot_id':>20}  오류")
    for r in records:
        rng = r.get("range") or {}
        span = f"{rng.get('start', '-')}~{rng.get('end', '-')}"
        rows = r.get("rows")
        print(
            f"{r.get('started_at', '-'):<26} {str(r.get('result')):<10} {span:<24} "
            f"{rows if rows is not None else '-':>10} {str(r.get('snapshot_id') or '-'):>20}  "
            f"{r.get('error') or ''}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--profile")
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument(
        "--state-machine-arn",
        default=f"arn:aws:states:{DEFAULT_REGION}:{DEFAULT_ACCOUNT}:stateMachine:{DEFAULT_STATE_MACHINE}",
    )
    p.add_argument("--bucket", default=DEFAULT_BUCKET)
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backfill", help="처음 전체 생성: Silver 묶음별 → ML-ready 한 번")
    b.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    b.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    b.add_argument("--chunk-days", type=int, default=5)
    b.add_argument("--dry-run", action="store_true")

    r = sub.add_parser("rerun", help="범위를 지정해 다시 실행")
    r.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    r.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    r.add_argument("--stage", choices=STAGES, default="all")
    r.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("runs", help="최근 실행 기록 표")
    s.add_argument("--table", choices=sorted(RUNS_PREFIX), default="ktms")
    s.add_argument("--last", type=int, default=5)
    return p.parse_args(argv)


def main(argv: list[str] | None = None, session=None, sleep=time.sleep, now=None) -> int:
    args = parse_args(argv)
    if session is None:
        import boto3

        session = boto3.Session(profile_name=args.profile, region_name=args.region)

    if args.command == "runs":
        print_runs(list_runs(session.client("s3"), args.bucket, args.table, args.last))
        return 0

    if args.command == "backfill":
        steps = plan_backfill(args.start, args.end, args.chunk_days)
    else:
        if args.start > args.end:
            raise SystemExit(f"--from({args.start})가 --to({args.end})보다 늦다")
        if args.stage in ("all", "silver") and (args.end - args.start).days + 1 > 7:
            raise SystemExit("Silver는 한 번에 7일까지다. 긴 범위는 backfill을 쓴다")
        steps = [Step(args.stage, args.start, args.end)]
    sfn = None if args.dry_run else session.client("stepfunctions")
    return run_steps(sfn, args.state_machine_arn, steps, args.dry_run, sleep=sleep, now=now)


if __name__ == "__main__":
    sys.exit(main())
