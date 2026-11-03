import gzip
import json
import os
from datetime import datetime, timedelta, timezone
import boto3
from botocore.exceptions import ClientError

BUCKET = os.environ["BRONZE_BUCKET"]
PREFIX = "tms_cleansys"
REPORT_PREFIX = "reports/missing_rate"
KST = timezone(timedelta(hours = 9))
SLOT_MINUTES = 30
s3 = boto3. client("s3")

# 시간 계산
## KST 시작, 끝 시각 UTC로 변환
def kst_day_range_utc(day: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo = KST).astimezone(timezone.utc)
    return start, start + timedelta(days = 1)

## 하루에 생성되야 할 슬롯 개수(48개)
def expected_slots(day: str) -> list[str]:
    start = datetime.strptime(day, "%Y-%m-%d")
    return[
        (start + timedelta(minutes = SLOT_MINUTES * i)).strftime("%Y-%m-%d %H:%M")
        for i in range(24 * 60 // SLOT_MINUTES)
    ]

## 폴더 이름의 run_ts를 UTC 시각으로 변환
def run_ts_of(run_prefix: str) -> datetime:
    stamp = run_prefix.rsplit("run_ts=", 1)[1]
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo = timezone.utc)

# 저장소 읽기
## 해당 UTC 날짜 아래의 run_ts 폴더 경로를 중복 없이 반환
def list_run_prefixes(ingest_date: str) -> list[str]:
    runs = set()
    prefix = f"{PREFIX}/ingest_date={ingest_date}/"
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket = BUCKET, Prefix = prefix):
        for obj in page.get("Contents", []):
            runs.add(obj["Key"].rsplit("/", 1)[0])
    return sorted(runs)

## 객체 bytes로 읽어오기(객체가 없으면 None)
def get_bytes(key: str) -> bytes | None:
    try:
        return s3.get_object(Bucket = BUCKET, Key = key)["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise

## 하나의 폴더 상태와 가장 최신 mesure_dt 반환
def summarize_run(run_prefix: str) -> dict:
    meta_bytes = get_bytes(f"{run_prefix}/snapshot.meta.json")
    if meta_bytes is None:
        return {"run": run_prefix, "status": "meta_missing", "latest": None}

    if not json.loads(meta_bytes).get("inspect", {}).get("ok"):
        return {"run": run_prefix, "status": "inspect_fail", "latest": None}

    raw_bytes = get_bytes(f"{run_prefix}/snapshot.json.gz")
    if raw_bytes is None:
        return {"run": run_prefix, "status": "raw_missing", "latest": None}

    items = json.loads(gzip.decompress(raw_bytes))["response"]["body"]["items"]
    latest = max((i["mesure_dt"] for i in items if i.get("mesure_dt")), default = None)
    return {"run": run_prefix, "status": "ok", "latest": latest}

# 계산, 저장
## 하루치 슬롯 누락 보고서 dict로 생성
def build_report(day: str) -> dict:
    d = datetime.strptime(day, "%Y-%m-%d")
    runs = []
    for ingest_date in ((d - timedelta(days = 1)).strftime("%Y-%m-%d"), day):
        runs += list_run_prefixes(ingest_date)

    start, end = kst_day_range_utc(day)
    summaries = [summarize_run(r) for r in runs]
    in_day = [s for s in summaries if start <= run_ts_of(s["run"]) < end]

    captured = {s["latest"] for s in summaries if s["status"] == "ok"}
    missing_slots = [s for s in expected_slots(day) if s not in captured]

    def count(status: str) -> list:
        return sum(1 for s in in_day if s["status"] == status)

    return {
        "target_date_kst": day,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec = "seconds"),
        "folders_in_day": len(in_day),
        "slots": {"expected": len(expected_slots(day)), "missing_count": len(missing_slots), "missing": missing_slots},
        "inspect_fail": count("inspect_fail"),
        "meta_missing": count("meta_missing"),
        "raw_missing": count("raw_missing"),
    }

## 보고서를 Json 형식으로 저장, 경로 반환
def save_report(day: str, report: dict) -> str:
    key = f"{REPORT_PREFIX}/date={day}/report.json"
    s3.put_object(
        Bucket = BUCKET,
        Key = key,
        Body = json.dumps(report, ensure_ascii = False, indent = 2).encode("utf-8"),
        ContentType = "application/json"
    )
    return key

#진입점
def target_days(event: dict) -> list[str]:
    if event.get("from"):
        start = datetime.strptime(event["from"], "%Y-%m-%d")
        end = datetime.strptime(event.get("to", event["from"]), "%Y-%m-%d")
        return [(start + timedelta(days = i)).strftime("%Y-%m-%d") for i in range((end - start).days + 1)]
    return [(datetime.now(KST) - timedelta(days = 1)).strftime("%Y-%m-%d")]

def lambda_handler(event, context):
    scheduled = not event.get("from")                       
    results = []
    for day in target_days(event):
        report = build_report(day)
        key = save_report(day, report)
        results.append({
            "date": day,
            "report_key": key,
            "missing_slots": report["slots"]["missing_count"],
            "inspect_fail": report["inspect_fail"],
        })
        print(json.dumps(results[-1], ensure_ascii = False))

    if scheduled and any(r["missing_slots"] > 0 for r in results):
        raise RuntimeError(f"슬롯 누락 발생: {results}")        
    return results