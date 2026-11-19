"""대시보드 관측 적재 Lambda (spec 012, contracts/load-interface.md).

상태 머신이 RDS 존재를 확인한 뒤 DB 주소를 넣어 부른다. VPC 안에서 돌고 NAT가 없으므로
S3(게이트웨이 엔드포인트)와 RDS 말고 다른 AWS API는 부르지 않는다(research R1).

mode
- recent: 최근 hours시간에 받은 원본 → C의 to_silver → UPSERT (늦게 온 정정 포함)
- daily : RDS 안에서 일일 요약 + 매핑 점검 (S3를 읽지 않음)
- day   : 그 KST 날짜 하루를 원본에서 UPSERT + 그 날짜 요약 (다시 채우기)
"""
from __future__ import annotations

import json
import os
import time
from datetime import UTC, date, datetime

import boto3

import db
import load

BUCKET = os.environ.get("BUCKET", "smokestack-tms-raw-952900391026")
DB_USER = os.environ.get("DB_USER", "tms_loader")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
DEFAULT_HOURS = float(os.environ.get("RECENT_HOURS", "4"))
MODES = ("recent", "daily", "day")


def parse_event(event: dict) -> dict:
    mode = event.get("mode")
    if mode not in MODES:
        raise ValueError(f"mode는 {MODES} 중 하나여야 한다: {mode!r}")
    if not event.get("db_host"):
        raise ValueError("db_host가 없다 (상태 머신이 RDS 확인 뒤 넣는다)")
    req = {"mode": mode, "db_host": event["db_host"], "db_port": int(event.get("db_port", 5432))}
    if mode == "recent":
        req["hours"] = float(event.get("hours", DEFAULT_HOURS))
    if mode == "day":
        if "date" not in event:
            raise ValueError("day에는 date(YYYY-MM-DD)가 필요하다")
        req["date"] = date.fromisoformat(event["date"])
    return req


def kst_today(now: datetime) -> date:
    return (now.astimezone(UTC) + load.KST).date()


def _load_rows(conn, silver, load_path: str, now: datetime, day: date) -> dict:
    rows = load.prepare_rows(silver)
    upserted, unchanged = db.upsert_measurements(conn, rows, load_path, now)
    new_keys = db.add_stack_keys(conn, rows, day)
    return {"read": len(rows), "upserted": upserted, "unchanged": unchanged}, new_keys


def run(req: dict, conn, s3, now: datetime) -> dict:
    mode, today = req["mode"], kst_today(now)
    out = {"mode": mode, "rows": {"read": 0, "upserted": 0, "unchanged": 0}, "new_stack_keys": 0,
           "summary_days": [], "new_names": [], "source": {}}
    if mode == "recent":
        silver, info = load.read_recent(BUCKET, now, req["hours"], s3)
        out["rows"], out["new_stack_keys"] = _load_rows(conn, silver, "recent", now, today)
        out["source"] = {"prefix": "tms_cleansys/", **info}
        if not silver.empty:
            ts = silver["ts_kst"]
            out["measured_range"] = {"min": str(ts.min()), "max": str(ts.max())}
    elif mode == "day":
        silver, info = load.read_day(BUCKET, req["date"], now, s3)
        out["rows"], out["new_stack_keys"] = _load_rows(conn, silver, "backfill", now, req["date"])
        db.refresh_daily_summaries(conn, [req["date"]], now)
        out["summary_days"] = [req["date"].isoformat()]
        out["source"] = {"prefix": "tms_cleansys/", "date": req["date"].isoformat(), **info}
    else:  # daily
        days = db.summary_days(conn, today)
        db.refresh_daily_summaries(conn, days, now)
        out["summary_days"] = [d.isoformat() for d in days]
        out["new_names"] = db.mapping_check(conn, date.fromordinal(today.toordinal() - 1), now)
    return out


def handler(event, context=None):
    started = datetime.now(UTC)
    t0 = time.monotonic()
    req = parse_event(event)
    conn = db.connect(req["db_host"], req["db_port"], DB_USER, region=REGION)
    try:
        out = run(req, conn, boto3.client("s3", region_name=REGION), started)
        out["run_id"] = f"{started:%Y%m%dT%H%M%SZ}-{req['mode']}"
        out["elapsed_s"] = round(time.monotonic() - t0, 1)
        db.record_run(conn, {**out, "started_at": started, "finished_at": datetime.now(UTC),
                             "result": "succeeded"})
    finally:
        conn.close()
    # 요약만 남긴다. 원본 값·비밀은 찍지 않는다.
    print(json.dumps({k: v for k, v in out.items() if k != "new_names"} | {"new_names": len(out["new_names"])},
                     ensure_ascii=False, default=str))
    return out
