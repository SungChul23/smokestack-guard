"""K-TMS ML-ready 계약 검사 Lambda (spec 010). 매일 갱신 상태 머신의 ML-ready 다음 단계.

- 판정 규칙은 C의 `smokestack_guard.silver.ml_ready_check`를 수정 없이 쓴다(PR #52).
  다만 `check()`는 받은 행 전체를 재계산·비교해서,
  재계산만 "여유 구간까지 계산하고 대상 범위만 비교"로 감싼다(research R5).
  비교 규칙과 상수는 그 모듈 것을 그대로 쓴다.
- 범위와 스냅샷은 같은 실행의 ML-ready 실행 기록에서 읽는다.
  `stage=check`면 입력 날짜와 최신 스냅샷(R3).
- 읽기 전용이다. 쓰는 곳은 자기 실행 기록 `silver2/_runs/ktms_ml_ready_check/`뿐이다(FR-012).
- 알림은 보내지 않고 제목·본문만 만들어 돌려준다. 상태 머신이 발행한다(R7).

계약: specs/a-platform/010-ml-ready-contract-check/contracts/check-interface.md
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, date, datetime, timedelta

# 규칙 패키지 레이어(smokestack_guard.zip)는 /opt/smokestack_guard로 풀린다(research R2).
if os.path.isdir("/opt/smokestack_guard") and "/opt" not in sys.path:
    sys.path.insert(0, "/opt")

import pandas as pd  # noqa: E402
from smokestack_guard.silver import ml_ready  # noqa: E402
from smokestack_guard.silver import ml_ready_check as mc  # noqa: E402

import ktms_pipeline as kp  # noqa: E402

DEFAULT_TABLE = "tms_silver2.ktms_ml_ready"
RUNS_PREFIX = "silver2/_runs/ktms_ml_ready_check"
ML_READY_RUNS_PREFIX = "silver2/_runs/ktms_ml_ready"
STATE_MACHINE = "tms-silver2-ktms"
MODES = ("observe", "block")
STAGES = ("all", "silver", "ml_ready", "check")
MAX_LINES = 10
ATOL = 1e-4
TS_COL = "measured_at"
KIND_ORDER = ("format", "rule", "recompute", "overlap")
KIND_LABEL = {"format": "형식", "rule": "규칙", "recompute": "재계산", "overlap": "겹침"}
DOC = "specs/a-platform/010-ml-ready-contract-check/contracts/check-interface.md"

# ---------------------------------------------------------------------------
# 입력
# ---------------------------------------------------------------------------


def _bool(value, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise ValueError(f"{name}는 true 또는 false여야 한다: {value!r}")


def parse_event(event: dict) -> dict:
    """data-model §1. 상태 머신 입력(args)에 기본값을 채운다."""
    args = dict(event.get("args") or {})
    p = {
        "start_date": args.get("start_date") or kp.AUTO,
        "end_date": args.get("end_date") or kp.AUTO,
        "stage": args.get("stage") or "all",
        "notify": _bool(args.get("notify", True), "notify"),
        "check_table": args.get("check_table") or DEFAULT_TABLE,
        "expect_source": args.get("expect_source") or None,
        "real_table": args.get("real_table") or None,
        "mode": args.get("mode") or event.get("mode") or "observe",
        "ml_ready_job_run_id": event.get("ml_ready_job_run_id") or None,
        "sfn_execution": event.get("sfn_execution") or "manual",
    }
    if p["mode"] not in MODES:
        raise ValueError(f"mode는 {MODES} 중 하나여야 한다: {p['mode']!r}")
    if p["stage"] not in STAGES:
        raise ValueError(f"stage는 {STAGES} 중 하나여야 한다: {p['stage']!r}")
    for name in ("check_table", "real_table"):
        if p[name] is not None and p[name].count(".") != 1:
            raise ValueError(f"{name}는 <db>.<table>이어야 한다: {p[name]!r}")
    return p


# ---------------------------------------------------------------------------
# 범위·스냅샷·읽기
# ---------------------------------------------------------------------------


def _quoted(table: str) -> str:
    db, name = table.split(".")
    return f'"{db}"."{name}"'


def latest_snapshot(query, table: str) -> int | None:
    db, name = table.split(".")
    df = query(
        f'SELECT snapshot_id FROM "{db}"."{name}$snapshots" ORDER BY committed_at DESC LIMIT 1', db
    )
    return int(df.iloc[0, 0]) if len(df) else None


def runs_prefix(table: str) -> str:
    """ML-ready 잡의 실행 기록 경로. 테이블 이름 규칙 silver2/_runs/<테이블>(AGENTS.md)."""
    return f"silver2/_runs/{table.split('.')[1]}"


def find_ml_ready_record(
    s3, bucket: str, job_run_id: str, now: datetime, prefix: str = ML_READY_RUNS_PREFIX
) -> tuple[str, dict]:
    """같은 실행의 ML-ready 기록(`<시작 UTC>_<job_run_id>.json`). 최근 이틀 안에서 찾는다."""
    start_after = f"{prefix}/{(now - timedelta(days=2)).astimezone(UTC):%Y%m%dT}"
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/", StartAfter=start_after):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(f"_{job_run_id}.json"):
                body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
                return f"s3://{bucket}/{obj['Key']}", json.loads(body)
    raise LookupError(f"ML-ready 실행 기록을 찾지 못했다: *_{job_run_id}.json")


def resolve_target(p: dict, s3, bucket: str, query, now: datetime) -> dict:
    """research R3. 검사할 범위·스냅샷과 그 출처."""
    if p["ml_ready_job_run_id"]:
        where, rec = find_ml_ready_record(
            s3, bucket, p["ml_ready_job_run_id"], now, runs_prefix(p["check_table"])
        )
        if rec.get("result") != "succeeded" or not rec.get("range"):
            raise ValueError(f"ML-ready 기록이 성공이 아니다: {where} result={rec.get('result')}")
        r = kp.DayRange(
            date.fromisoformat(rec["range"]["start"]), date.fromisoformat(rec["range"]["end"])
        )
        sid = rec.get("snapshot_id")
        return {
            "range": r,
            "snapshot_id": int(sid)
            if sid is not None
            else latest_snapshot(query, p["check_table"]),
            "range_source": "ml_ready_run",
            "ml_ready_run_record": where,
        }
    r = kp.resolve_range(p["start_date"], p["end_date"], now=now)
    return {
        "range": r,
        "snapshot_id": latest_snapshot(query, p["check_table"]),
        "range_source": "input",
        "ml_ready_run_record": None,
    }


def read_window(query, table: str, snapshot_id: int | None, lo: datetime, hi: datetime):
    """[lo, hi] 양 끝 포함. 스냅샷이 있으면 그 시점으로 읽는다(research R4)."""
    version = f" FOR VERSION AS OF {int(snapshot_id)}" if snapshot_id is not None else ""
    sql = (
        f"SELECT * FROM {_quoted(table)}{version} "
        f"WHERE {TS_COL} BETWEEN TIMESTAMP '{lo:%Y-%m-%d %H:%M:%S}' "
        f"AND TIMESTAMP '{hi:%Y-%m-%d %H:%M:%S}'"
    )
    return query(sql, table.split(".")[0])


def read_stacks(query, table: str, r: kp.DayRange) -> set[str]:
    sql = (
        f"SELECT DISTINCT stack_code FROM {_quoted(table)} "
        f"WHERE {TS_COL} >= TIMESTAMP '{r.start_ts:%Y-%m-%d %H:%M:%S}' "
        f"AND {TS_COL} < TIMESTAMP '{r.end_ts:%Y-%m-%d %H:%M:%S}'"
    )
    return set(query(sql, table.split(".")[0])["stack_code"].astype(str))


def athena_query(workgroup: str):
    def run(sql: str, database: str) -> pd.DataFrame:
        import awswrangler as wr

        return wr.athena.read_sql_query(
            sql, database=database, workgroup=workgroup, ctas_approach=False
        )

    return run


# ---------------------------------------------------------------------------
# 판정
# ---------------------------------------------------------------------------


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Athena가 주는 확장 dtype(boolean, string, Int64)을 C 규칙이 다루는 numpy dtype으로 바꾼다."""
    out = df.copy()
    for col in out.columns:
        dt = out[col].dtype
        if isinstance(dt, pd.BooleanDtype):
            out[col] = out[col].astype(object).where(out[col].notna(), None)
            if out[col].notna().all():
                out[col] = out[col].astype(bool)
        elif isinstance(dt, pd.StringDtype):
            out[col] = out[col].astype(object).where(out[col].notna(), None)
        elif pd.api.types.is_extension_array_dtype(dt) and pd.api.types.is_numeric_dtype(dt):
            out[col] = out[col].astype("float64")
    if TS_COL in out.columns:
        ts = pd.to_datetime(out[TS_COL])
        if ts.dt.tz is not None:
            ts = ts.dt.tz_localize(None)
        out[TS_COL] = ts.astype("datetime64[ns]")
    return out


def _in_range(df: pd.DataFrame, r: kp.DayRange) -> pd.Series:
    return (df[TS_COL] >= r.start_ts) & (df[TS_COL] < r.end_ts)


def recompute_in_range(window: pd.DataFrame, r: kp.DayRange, atol: float = ATOL) -> list[str]:
    """`ml_ready_check._recompute_checks`와 같은 비교를 대상 범위 행에만 한다.

    재계산은 창 전체(앞 150분, 다음날 00:30까지)로 해서
    범위 첫 행의 과거·마지막 행의 미래가 채워진다.
    """
    again = ml_ready.to_ml_ready(window[mc.SOURCE_COLUMNS].copy(), data_source="check")
    again = again[_in_range(again, r)].sort_values(mc.KEY).reset_index(drop=True)
    cur = window[_in_range(window, r)].sort_values(mc.KEY).reset_index(drop=True)
    if len(again) != len(cur):
        return [f"재계산 행 수 {len(again)} != 테이블 {len(cur)}"]
    bad = []
    for col in ml_ready.COLUMNS:
        if col in mc.SKIP_RECOMPUTE or col in mc.KEY:
            continue
        a, b = again[col], cur[col]
        if a.dtype == bool or b.dtype == bool or a.dtype == object:
            diff = a.astype("object").fillna(-1).ne(b.astype("object").fillna(-1))
        else:
            a, b = a.astype("float64"), b.astype("float64")
            diff = ~((a - b).abs() <= atol) & ~(a.isna() & b.isna())
        if diff.any():
            first = cur.loc[diff.idxmax(), mc.KEY].tolist()
            bad.append(f"재계산 불일치 {col}: {int(diff.sum())}행 (첫 행 {first})")
    return bad


def evaluate(
    window: pd.DataFrame,
    r: kp.DayRange,
    expect_source: str | None = None,
    real_stacks: set[str] | None = None,
) -> list[dict]:
    """위반 항목 목록(data-model §3). 비어 있으면 통과."""
    window = normalize(window)
    target = window[_in_range(window, r)].reset_index(drop=True) if TS_COL in window else window
    if target.empty and list(window.columns) == ml_ready.COLUMNS:
        return []  # 행이 없으면 값 검사는 의미가 없다. 결과는 empty로 따로 알린다
    out = [{"kind": "format", "text": t} for t in mc._format_checks(target, expect_source)]
    if list(window.columns) != ml_ready.COLUMNS:
        return out  # 컬럼이 다르면 C의 check()처럼 나머지는 건너뛴다
    out += [{"kind": "rule", "text": t} for t in mc._rule_checks(target)]
    out += [{"kind": "recompute", "text": t} for t in recompute_in_range(window, r)]
    if real_stacks:
        shared = set(target["stack_code"].unique()) & real_stacks
        if shared:
            text = f"실데이터와 굴뚝 키가 겹친다: {len(shared)}개 (예: {sorted(shared)[:3]})"
            out.append({"kind": "overlap", "text": text})
    return out


# ---------------------------------------------------------------------------
# 알림 문안 (contracts §4). 제목은 SNS 제약으로 ASCII만.
# ---------------------------------------------------------------------------


def rerun_command(account: str, r: dict, table: str) -> str:
    payload = {"stage": "check", "start_date": r["start"], "end_date": r["end"]}
    if table != DEFAULT_TABLE:
        payload["check_table"] = table
    arn = f"arn:aws:states:ap-northeast-2:{account}:stateMachine:{STATE_MACHINE}"
    return (
        "aws stepfunctions start-execution --region ap-northeast-2 "
        f"--state-machine-arn {arn} --input '{json.dumps(payload)}'"
    )


def format_alert(out: dict, account: str = "<account>") -> tuple[str, str]:
    if out["result"] == "passed":
        return "", ""
    r, table = out["range"], out["table"]
    short = table.split(".")[-1]
    head = [
        f"테이블: {table}",
        f"범위: {r['start']} ~ {r['end']} ({out['rows']:,}행)",
        f"스냅샷: {out['snapshot_id']}",
    ]
    tail = [
        "",
        f"실행 기록: {out['run_record']}",
        f"검사만 다시: {rerun_command(account, r, table)}",
        f"읽는 법: {DOC}",
        f"실행 이름: {out['sfn_execution']}",
    ]
    if out["result"] == "empty":
        subject = f"[tms] K-TMS contract check: no rows - {short} {r['start']}~{r['end']}"
        body = [
            "K-TMS ML-ready 계약 검사: 대상 범위에 행이 없다",
            "",
            *head,
            "수집 공백이면 누락률 리포트를 확인한다.",
            *tail,
        ]
        return subject, "\n".join(body)

    items = sorted(out["violation_list"], key=lambda v: KIND_ORDER.index(v["kind"]))
    n = len(items)
    lines = [f"[{KIND_LABEL[v['kind']]}] {v['text']}" for v in items[:MAX_LINES]]
    if n > MAX_LINES:
        lines.append(f"… 외 {n - MAX_LINES}건 (전체는 실행 기록)")
    effect = (
        "block (실행 실패 처리, 데이터는 이미 커밋됨)"
        if out["mode"] == "block"
        else "observe (실행은 성공 처리, 데이터는 이미 커밋됨)"
    )
    subject = f"[tms] K-TMS contract violation - {short} {r['start']}~{r['end']} ({n})"
    body = [
        f"K-TMS ML-ready 계약 위반 ({n}건)",
        "",
        *head,
        f"모드: {effect}",
        "",
        *lines,
        *tail[:2],
        "학습: 이 스냅샷 대신 마지막 통과 스냅샷을 쓴다 (008 contracts/ktms-tables.md)",
        *tail[2:],
    ]
    return subject, "\n".join(body)


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def run(event: dict, s3, query, bucket: str, request_id: str, account: str, now=None) -> dict:
    started_at = now or datetime.now(UTC)
    p = parse_event(event)
    key = kp.run_record_key(RUNS_PREFIX, started_at, request_id)
    run_record = f"s3://{bucket}/{key}"
    record: dict = {
        "table": p["check_table"],
        "range": None,
        "snapshot_id": None,
        "range_source": None,
        "ml_ready_run_record": None,
        "window": None,
        "rows": None,
        "window_rows": None,
        "result": None,
        "violations": None,
        "error": None,
        "mode": p["mode"],
        "notify": p["notify"],
        "expect_source": p["expect_source"],
        "real_table": p["real_table"],
        "sfn_execution": p["sfn_execution"],
        "request_id": request_id,
        "versions": kp.runtime_versions(),
        "started_at": kp.iso(started_at),
        "finished_at": None,
    }
    try:
        t = resolve_target(p, s3, bucket, query, started_at)
        r = t["range"]
        lo, hi = kp.ml_ready_window(r)
        record |= {
            "range": r.to_dict(),
            "snapshot_id": t["snapshot_id"],
            "range_source": t["range_source"],
            "ml_ready_run_record": t["ml_ready_run_record"],
            "window": [lo.isoformat(), hi.isoformat()],
        }
        window = read_window(query, p["check_table"], t["snapshot_id"], lo, hi)
        real = read_stacks(query, p["real_table"], r) if p["real_table"] else None
        violations = evaluate(window, r, p["expect_source"], real)
        rows = int(_in_range(normalize(window), r).sum()) if len(window) else 0
        result = "violation" if violations else ("empty" if rows == 0 else "passed")
        record |= {
            "rows": rows,
            "window_rows": int(len(window)),
            "result": result,
            "violations": violations,
        }
    except Exception as exc:
        record = kp.failure_record(record, exc)
        record["finished_at"] = kp.iso(datetime.now(UTC))
        kp.write_run_record(record, bucket, key, s3=s3)
        print(
            json.dumps(
                {"result": "failed", "error": record["error"], "run_record": run_record},
                ensure_ascii=False,
            )
        )
        raise

    record["finished_at"] = kp.iso(datetime.now(UTC))
    kp.write_run_record(record, bucket, key, s3=s3)
    out = {
        "result": record["result"],
        "table": record["table"],
        "range": record["range"],
        "snapshot_id": record["snapshot_id"],
        "rows": record["rows"],
        "violations": len(record["violations"]),
        "run_record": run_record,
        "mode": p["mode"],
        "sfn_execution": p["sfn_execution"],
        "violation_list": record["violations"],
    }
    out["subject"], out["message"] = format_alert(out, account)
    out["block"] = out["result"] == "violation" and p["mode"] == "block"
    del out["violation_list"]  # 상태 머신 출력 한도(256KB) 안에 두기 위해 목록은 기록에만 둔다
    print(
        json.dumps(
            {k: out[k] for k in ("result", "table", "range", "rows", "violations", "run_record")},
            ensure_ascii=False,
        )
    )
    return out


def handler(event, context):
    import boto3

    bucket = os.environ["BUCKET"]
    workgroup = os.environ["ATHENA_WORKGROUP"]
    account = context.invoked_function_arn.split(":")[4]
    return run(
        event, boto3.client("s3"), athena_query(workgroup), bucket, context.aws_request_id, account
    )
