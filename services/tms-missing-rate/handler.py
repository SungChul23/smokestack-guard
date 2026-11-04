# Bronze 슬롯 누락률 일일 리포트 Lambda
# 출처: B(olchangiagi)의 k-tms-bronze 브랜치 k_tms_pipeline/lambda/missing_rate_lambda.py (커밋 124f079)
# 바꾼 점: 누락 시 예외 대신 SNS로 요약 알림을 보낸다 (specs/a-platform/002-missing-rate-report/research.md R2)
import gzip
import json
import os
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

BUCKET = os.environ["BRONZE_BUCKET"]                 # 원본 버킷 (읽기: tms_cleansys/, 쓰기: reports/missing_rate/)
ALERT_TOPIC_ARN = os.environ["ALERT_TOPIC_ARN"]      # 누락 알림을 보낼 SNS 토픽
PREFIX = "tms_cleansys"
REPORT_PREFIX = "reports/missing_rate"
KST = timezone(timedelta(hours = 9))
SLOT_MINUTES = 30

s3 = boto3.client("s3")                              # 핸들러 밖에서 생성해 재사용
sns = boto3.client("sns")


# 시간 계산
## KST 하루의 시작, 끝 시각을 UTC로 변환
def kst_day_range_utc(day: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo = KST).astimezone(timezone.utc)
    return start, start + timedelta(days = 1)

## 하루에 있어야 할 슬롯 목록 (30분 단위 48개, mesure_dt와 같은 "YYYY-MM-DD HH:MM" 형식)
def expected_slots(day: str) -> list[str]:
    start = datetime.strptime(day, "%Y-%m-%d")
    return [
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

## 객체를 bytes로 읽기 (객체가 없으면 None)
def get_bytes(key: str) -> bytes | None:
    try:
        return s3.get_object(Bucket = BUCKET, Key = key)["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise

## 폴더 하나의 상태와 가장 최신 mesure_dt 반환
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
## 하루치 슬롯 누락 리포트 생성 (contracts/report.schema.json)
def build_report(day: str) -> dict:
    d = datetime.strptime(day, "%Y-%m-%d")
    runs = []
    for ingest_date in ((d - timedelta(days = 1)).strftime("%Y-%m-%d"), day):    # KST 하루는 UTC 이틀에 걸친다
        runs += list_run_prefixes(ingest_date)

    start, end = kst_day_range_utc(day)
    summaries = [summarize_run(r) for r in runs]
    in_day = [s for s in summaries if start <= run_ts_of(s["run"]) < end]

    captured = {s["latest"] for s in summaries if s["status"] == "ok"}          # 반영 지연 때문에 이틀치 전체에서 찾는다
    missing_slots = [s for s in expected_slots(day) if s not in captured]       # 시간 순

    def count(status: str) -> int:                                               # 상태별 폴더 수는 대상 하루 기준
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

## 리포트를 JSON으로 저장하고 키 반환 (같은 날짜를 다시 계산하면 덮어쓴다)
def save_report(day: str, report: dict) -> str:
    key = f"{REPORT_PREFIX}/date={day}/report.json"
    s3.put_object(
        Bucket = BUCKET,
        Key = key,
        Body = json.dumps(report, ensure_ascii = False, indent = 2).encode("utf-8"),
        ContentType = "application/json"
    )
    return key


# 알림
## 누락 알림 제목과 본문 (contracts/alert-message.md). 원문 측정값, 키, 이메일은 넣지 않는다
def build_alert(report: dict, report_key: str) -> tuple[str, str]:
    slots = report["slots"]
    day = report["target_date_kst"]
    subject = f"[TMS] {day} 슬롯 누락 {slots['missing_count']}개"
    lines = [
        f"대상 날짜(KST): {day}",
        f"누락 슬롯: {slots['missing_count']} / {slots['expected']} ({slots['missing_count'] / slots['expected']:.1%})",
        *(f"- {slot}" for slot in slots["missing"]),
        f"점검 실패 폴더: {report['inspect_fail']} · 메타 없음: {report['meta_missing']} · 원문 없음: {report['raw_missing']}",
        f"리포트: s3://{BUCKET}/{report_key}",
    ]
    return subject, "\n".join(lines)


# 진입점
## 대상 날짜 목록: 수동 실행은 {"from", "to"} (contracts/invoke-event.md), 자동 실행은 어제(KST)
def target_days(event: dict) -> list[str]:
    if event.get("from"):
        start = datetime.strptime(event["from"], "%Y-%m-%d")
        end = datetime.strptime(event.get("to", event["from"]), "%Y-%m-%d")
        return [(start + timedelta(days = i)).strftime("%Y-%m-%d") for i in range((end - start).days + 1)]
    return [(datetime.now(KST) - timedelta(days = 1)).strftime("%Y-%m-%d")]

def lambda_handler(event, context):
    scheduled = not event.get("from")                                           # 수동 실행(백필)은 알리지 않는다
    results = []
    for day in target_days(event):
        report = build_report(day)
        key = save_report(day, report)
        result = {
            "date": day,
            "report_key": key,
            "missing_slots": report["slots"]["missing_count"],
            "inspect_fail": report["inspect_fail"],
        }
        if scheduled:
            result["alerted"] = result["missing_slots"] > 0
            if result["alerted"]:                                               # 누락은 예외가 아니라 알림으로 처리한다
                subject, message = build_alert(report, key)
                sns.publish(TopicArn = ALERT_TOPIC_ARN, Subject = subject, Message = message)
        results.append(result)
        print(json.dumps(result, ensure_ascii = False))                         # 요약만 남긴다
    return results
