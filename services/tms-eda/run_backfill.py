"""TW CEMS 원본 월 파일을 Glue Job으로 한 번에 Parquet 변환한다 (사람이 실행하는 백필 명령).

- 원본 버킷에서 `YYYY-MM.jsonl` 월 파일을 찾아 범위 안의 월만 대상으로 삼는다.
- 월마다 Job을 시작하고 30초마다 상태를 확인한다. 실패한 월은 1회만 다시 시작한다.
- 끝나면 월별 결과 표, 합계 추정 비용, 실패 목록을 출력한다.

자격증명은 실행자의 환경 변수나 `--profile`에서 읽는다. 코드에 쓰지 않는다.
계약: specs/a-platform/003-tw-cems-eda/contracts/run-interface.md §2
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from botocore.exceptions import ClientError

DEFAULT_FROM = "2024-11"
DEFAULT_TO = "2026-10"
DEFAULT_JOB_NAME = "tms-eda-tw-cems-parquet"
DEFAULT_CRAWLER_NAME = "tms-eda-tw-cems-crawler"
DEFAULT_RAW_BUCKET = "smokestack-tms-raw-952900391026"
DEFAULT_RAW_PREFIX = "bronze/tw_cems/historical"
DEFAULT_EDA_BUCKET = "smokestack-tms-eda-952900391026"
DEFAULT_OUTPUT_PREFIX = "tw_cems_raw"
DEFAULT_REGION = "ap-northeast-2"

MAX_CONCURRENCY = 6  # Job의 max_concurrent_runs와 같다
MAX_ATTEMPTS = 2  # 첫 시도 + 재시도 1회
POLL_SECONDS = 30
USD_PER_DPU_HOUR = 0.308  # Glue Standard, ap-northeast-2

SUCCEEDED = "SUCCEEDED"
SKIPPED = "SKIPPED"
FAILED_STATES = frozenset({"FAILED", "ERROR", "TIMEOUT", "STOPPED"})
START_FAILED = "ERROR"  # start_job_run 자체가 거절된 경우

_MONTH_FILE_RE = re.compile(r"^(\d{4})-(\d{2})\.jsonl$")
_MONTH_ARG_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class RawObject:
    key: str
    size: int
    last_modified: datetime


@dataclass
class MonthTarget:
    month: str  # YYYY-MM
    key: str
    size: int
    last_modified: datetime
    skipped: bool = False


@dataclass
class MonthResult:
    month: str
    state: str
    attempts: int
    run_id: str | None
    execution_s: int | None
    dpu_s: float | None
    est_usd: float | None


# ---------------------------------------------------------------------------
# 인자
# ---------------------------------------------------------------------------


def _month_arg(value: str) -> str:
    if not _MONTH_ARG_RE.match(value):
        raise argparse.ArgumentTypeError(f"YYYY-MM 형식이어야 한다: {value!r}")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="from_month", type=_month_arg, default=DEFAULT_FROM)
    parser.add_argument("--to", dest="to_month", type=_month_arg, default=DEFAULT_TO)
    parser.add_argument(
        "--concurrency", type=int, default=MAX_CONCURRENCY, help="동시 실행 수 (1~6)"
    )
    parser.add_argument("--only-missing", action="store_true", help="_SUCCESS가 있는 월은 건너뜀")
    parser.add_argument("--dry-run", action="store_true", help="대상만 출력하고 시작하지 않음")
    parser.add_argument("--start-crawler", action="store_true", help="모두 성공하면 크롤러 시작")
    parser.add_argument("--job-name", default=DEFAULT_JOB_NAME)
    parser.add_argument("--crawler-name", default=DEFAULT_CRAWLER_NAME)
    parser.add_argument("--raw-bucket", default=DEFAULT_RAW_BUCKET)
    parser.add_argument("--raw-prefix", default=DEFAULT_RAW_PREFIX)
    parser.add_argument("--eda-bucket", default=DEFAULT_EDA_BUCKET)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--profile", default=None, help="AWS 프로필 이름")
    parser.add_argument("--region", default=DEFAULT_REGION)

    args = parser.parse_args(argv)
    if not 1 <= args.concurrency <= MAX_CONCURRENCY:
        parser.error(f"--concurrency는 1~{MAX_CONCURRENCY}이어야 한다: {args.concurrency}")
    if args.from_month > args.to_month:
        parser.error(f"--from({args.from_month})이 --to({args.to_month})보다 늦다")
    return args


# ---------------------------------------------------------------------------
# 대상 월 찾기
# ---------------------------------------------------------------------------


def _months_between(from_month: str, to_month: str) -> list[str]:
    year, month = int(from_month[:4]), int(from_month[5:])
    end = (int(to_month[:4]), int(to_month[5:]))
    months = []
    while (year, month) <= end:
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def list_raw_keys(s3, bucket: str, prefix: str) -> list[RawObject]:
    """원본 경로 바로 아래 객체 목록을 페이지 단위로 모두 읽는다.

    Job은 `{prefix}/YYYY-MM.jsonl`만 읽으므로 하위 폴더의 객체는 제외한다.
    """
    prefix = prefix.strip("/") + "/"
    objects = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            if "/" in item["Key"][len(prefix) :]:
                continue
            objects.append(RawObject(item["Key"], item["Size"], item["LastModified"]))
    return objects


def parse_months(
    objects: Iterable[RawObject], from_month: str, to_month: str
) -> tuple[list[MonthTarget], list[str]]:
    """(범위 안 대상 월, 범위 안에서 원본에 없는 월)을 돌려준다."""
    in_range = _months_between(from_month, to_month)
    wanted = set(in_range)
    found: dict[str, MonthTarget] = {}
    for obj in objects:
        name = obj.key.rsplit("/", 1)[-1]
        match = _MONTH_FILE_RE.match(name)
        if not match:
            continue
        month = f"{match.group(1)}-{match.group(2)}"
        if month in wanted:
            found[month] = MonthTarget(month, obj.key, obj.size, obj.last_modified)
    targets = [found[m] for m in in_range if m in found]
    missing = [m for m in in_range if m not in found]
    return targets, missing


def _success_key(output_prefix: str, month: str) -> str:
    return f"{output_prefix.strip('/')}/year={month[:4]}/month={month[5:]}/_SUCCESS"


def _object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
    return True


def plan_targets(
    s3, targets: list[MonthTarget], eda_bucket: str, output_prefix: str, only_missing: bool
) -> list[MonthTarget]:
    """--only-missing이면 _SUCCESS가 이미 있는 월을 SKIPPED로 표시한다."""
    if only_missing:
        for target in targets:
            target.skipped = _object_exists(
                s3, eda_bucket, _success_key(output_prefix, target.month)
            )
    return targets


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def estimate_cost(job_run: dict) -> tuple[int | None, float | None, float | None]:
    """(execution_s, dpu_s, est_usd). DPUSeconds가 없으면 ExecutionTime × NumberOfWorkers."""
    execution_s = job_run.get("ExecutionTime")
    dpu_s = job_run.get("DPUSeconds")
    if dpu_s is None and execution_s is not None and job_run.get("NumberOfWorkers"):
        dpu_s = execution_s * job_run["NumberOfWorkers"]
    est_usd = None if dpu_s is None else round(dpu_s / 3600 * USD_PER_DPU_HOUR, 4)
    return execution_s, dpu_s, est_usd


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def _start(glue, job_name: str, month: str) -> str | None:
    """Job을 시작하고 JobRunId를 돌려준다. 시작 자체가 거절되면 None."""
    try:
        response = glue.start_job_run(
            JobName=job_name, Arguments={"--year": month[:4], "--month": month[5:]}
        )
    except ClientError as exc:
        _log(f"{month} 시작 실패: {exc.response.get('Error', {}).get('Code')}")
        return None
    _log(f"{month} 시작: {response['JobRunId']}")
    return response["JobRunId"]


def run_all(
    glue,
    months: list[str],
    job_name: str,
    concurrency: int,
    poll_seconds: float = POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[MonthResult]:
    """월별 Job을 동시에 `concurrency`개 이하로 돌리고, 실패한 월은 1회만 다시 시작한다."""
    pending = list(months)
    running: dict[str, tuple[str | None, int]] = {}  # month -> (run_id, attempts)
    results: dict[str, MonthResult] = {}

    while pending or running:
        while pending and len(running) < concurrency:
            month = pending.pop(0)
            running[month] = (_start(glue, job_name, month), 1)

        sleep(poll_seconds)

        for month, (run_id, attempts) in list(running.items()):
            if run_id is None:
                job_run: dict = {}
                state = START_FAILED
            else:
                job_run = glue.get_job_run(JobName=job_name, RunId=run_id)["JobRun"]
                state = job_run["JobRunState"]

            if state != SUCCEEDED and state not in FAILED_STATES:
                continue  # 아직 진행 중

            if state in FAILED_STATES and attempts < MAX_ATTEMPTS:
                _log(f"{month} {state} → 재시도")
                # 같은 자리에서 다시 시작하므로 동시 실행 수가 늘지 않는다.
                running[month] = (_start(glue, job_name, month), attempts + 1)
                continue

            execution_s, dpu_s, est_usd = estimate_cost(job_run)
            results[month] = MonthResult(
                month, state, attempts, run_id, execution_s, dpu_s, est_usd
            )
            del running[month]
            _log(f"{month} {state} (시도 {attempts}회)")

    return [results[m] for m in months]


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------

_COLUMNS = ["month", "state", "attempts", "run_id", "execution_s", "dpu_s", "est_usd"]


def _cell(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}" if value < 10 else f"{value:.1f}"
    return str(value)


def render_table(results: list[MonthResult]) -> str:
    rows = [[_cell(getattr(r, c)) for c in _COLUMNS] for r in results]
    total_dpu = sum(r.dpu_s or 0 for r in results)
    total_usd = sum(r.est_usd or 0 for r in results)
    rows.append(["합계", "", "", "", "", _cell(float(total_dpu)), _cell(round(total_usd, 4))])

    widths = [max(len(c), *(len(row[i]) for row in rows)) for i, c in enumerate(_COLUMNS)]
    lines = [" | ".join(c.ljust(w) for c, w in zip(_COLUMNS, widths, strict=True))]
    lines.append("-+-".join("-" * w for w in widths))
    for row in rows:
        lines.append(" | ".join(v.ljust(w) for v, w in zip(row, widths, strict=True)))

    failed = [r.month for r in results if r.state not in (SUCCEEDED, SKIPPED)]
    lines.append("")
    lines.append(f"실패 목록 ({len(failed)}): {', '.join(failed) if failed else '없음'}")
    return "\n".join(lines)


def _render_plan(targets: list[MonthTarget], missing: list[str]) -> str:
    lines = ["month   | size_gb | last_modified (UTC)       | plan"]
    for t in targets:
        plan = SKIPPED if t.skipped else "RUN"
        lines.append(f"{t.month} | {t.size / 1e9:7.2f} | {t.last_modified.isoformat():25} | {plan}")
    lines.append("")
    skipped = sum(t.skipped for t in targets)
    lines.append(f"대상 {len(targets) - skipped}개월, SKIPPED {skipped}개월")
    lines.append(f"범위 안에서 원본에 없는 월 ({len(missing)}): {', '.join(missing) or '없음'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


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

    objects = list_raw_keys(s3, args.raw_bucket, args.raw_prefix)
    targets, missing = parse_months(objects, args.from_month, args.to_month)
    targets = plan_targets(s3, targets, args.eda_bucket, args.output_prefix, args.only_missing)

    print(_render_plan(targets, missing), flush=True)
    if args.dry_run:
        return 0

    to_run = [t.month for t in targets if not t.skipped]
    run_results = run_all(glue, to_run, args.job_name, args.concurrency, sleep=sleep)
    by_month = {r.month: r for r in run_results}
    results = [
        by_month.get(t.month) or MonthResult(t.month, SKIPPED, 0, None, None, None, None)
        for t in targets
    ]

    print()
    print(render_table(results), flush=True)

    failed = [r for r in results if r.state not in (SUCCEEDED, SKIPPED)]
    if args.start_crawler:
        if failed:
            print(f"경고: 실패한 월이 {len(failed)}개라 크롤러를 시작하지 않는다.", flush=True)
        else:
            try:
                glue.start_crawler(Name=args.crawler_name)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                print(f"크롤러 시작 실패: {code}", flush=True)
                return 1
            print(f"크롤러 시작: {args.crawler_name}", flush=True)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
