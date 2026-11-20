# ruff: noqa: E501  (한글 본문·메일 문구 줄이 길다)
"""학습 스냅샷 알림 Lambda (specs/a-platform/015-synthetic-v2-snapshot-notice, contracts/notice-format.md).

매일 05:00 KST. 실행 기록(silver2/_runs/…)만 읽어 실측·합성 각각
"계약 검사를 통과한 최근 스냅샷"(Silver·ML-ready)과 확정 범위를 메일로 보낸다. Athena를 쓰지 않는다.

- ML-ready 스냅샷: 계약 검사 기록(result=passed)의 snapshot_id
- Silver 스냅샷: 그 ML-ready 실행이 시작하기 전에 끝난 같은 출처의 마지막 성공 Silver 기록 (research R5)
- 확정 범위: 출처 첫날 ~ 실행일-2일 (008 매일 최근 이틀 재계산)

입력: {} | {"as_of": "YYYY-MM-DD"} | {"dry_run": true}
수신 주소는 SNS 구독(Terraform 변수)에만 있다. 이 파일에는 없다.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta

BUCKET = os.environ.get("BUCKET", "smokestack-tms-raw-952900391026")
TOPIC_ARN = os.environ.get("TOPIC_ARN", "")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
KST = timedelta(hours=9)
LOOKBACK_DAYS = 7
SHOW = 3
CHECK_PREFIX = "silver2/_runs/ktms_ml_ready_check"

SOURCES = {
    "ktms": {
        "label": "실측 K-TMS",
        "silver": "tms_silver2.ktms",
        "ml_ready": "tms_silver2.ktms_ml_ready",
        "silver_runs": "silver2/_runs/ktms",
        "first_day": date(2026, 10, 31),  # 학습 범위 통일: 실측 10/30은 오후부터라 둘 다 10/31부터 (2026-11-20 결정)
        "note": "",
    },
    "ktms_synth": {
        "label": "합성 K-TMS v2",
        "silver": "tms_silver2.ktms_synth",
        "ml_ready": "tms_silver2.ktms_synth_ml_ready",
        "silver_runs": "silver2/_runs/ktms_synth",
        "first_day": date(2026, 10, 31),  # 학습 범위 통일: 실측 10/30은 오후부터라 둘 다 10/31부터 (2026-11-20 결정)
        "note": " — 학습(Train)에만, 검증·평가에는 넣지 않음",
        # 생성기 v2로 다시 계산을 시작한 시각(UTC). 그 전 검사 기록은 v1 스냅샷이라 알리지 않는다 (2026-11-20)
        "since": "2026-11-20T07:41:00+00:00",
    },
}


# ---------------------------------------------------------------------------
# 기록 읽기
# ---------------------------------------------------------------------------


def _utc(iso: str) -> datetime:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(UTC)


def _kst_date(iso: str) -> date:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return (t.astimezone(UTC) + KST).date()


def list_records(s3, prefix: str, since: datetime) -> list[dict]:
    """기록 키는 `<prefix>/<시작 UTC %Y%m%dT%H%M%SZ>_<id>.json`이라 StartAfter로 최근 것만 본다."""
    out = []
    start_after = f"{prefix}/{since.astimezone(UTC):%Y%m%dT}"
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"{prefix}/", StartAfter=start_after):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(".json"):
                continue
            body = s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read()
            try:
                rec = json.loads(body)
            except ValueError:
                continue
            rec["_key"] = obj["Key"]
            out.append(rec)
    return out


def _ml_ready_started(s3, check: dict) -> str | None:
    """검사 기록이 가리키는 ML-ready 실행 기록의 시작 시각. 없으면 검사 시작 시각."""
    ref = check.get("ml_ready_run_record")
    if ref and ref.startswith(f"s3://{BUCKET}/"):
        key = ref[len(f"s3://{BUCKET}/"):]
        try:
            rec = json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
            return rec.get("started_at")
        except Exception:  # noqa: BLE001 - 기록이 없으면 검사 시각으로 대신한다
            pass
    return check.get("started_at")


def silver_snapshot_before(silver_runs: list[dict], before_iso: str | None) -> int | None:
    """before 이전에 끝난 마지막 성공 Silver 실행의 snapshot_id."""
    if not before_iso:
        return None
    ok = [
        r for r in silver_runs
        if r.get("result") == "succeeded" and r.get("snapshot_id") is not None
        and r.get("finished_at") and r["finished_at"] <= before_iso
    ]
    if not ok:
        return None
    return int(max(ok, key=lambda r: r["finished_at"])["snapshot_id"])


def collect(s3, as_of: date) -> dict:
    """출처별 [{run_date, result, silver_snapshot, ml_ready_snapshot, confirmed_to}] (최신 먼저)."""
    since = datetime.combine(as_of - timedelta(days=LOOKBACK_DAYS), datetime.min.time(), UTC)
    checks = [c for c in list_records(s3, CHECK_PREFIX, since) if c.get("started_at")]
    out = {}
    for src, cfg in SOURCES.items():
        since_v = cfg.get("since")
        mine = [
            c for c in checks
            if c.get("table") == cfg["ml_ready"] and _kst_date(c["started_at"]) <= as_of
            and (since_v is None or _utc(c["started_at"]) >= _utc(since_v))
        ]
        silver_runs = list_records(s3, cfg["silver_runs"], since - timedelta(days=1))
        by_day: dict[date, dict] = {}
        for c in sorted(mine, key=lambda c: c["started_at"]):
            by_day[_kst_date(c["started_at"])] = c  # 날짜마다 마지막 검사
        rows = []
        for day in sorted(by_day, reverse=True):
            c = by_day[day]
            row = {
                "run_date": day.isoformat(),
                "result": c.get("result"),
                "ml_ready_snapshot": c.get("snapshot_id"),
                "silver_snapshot": None,
                "confirmed_from": cfg["first_day"].isoformat(),
                "confirmed_to": (day - timedelta(days=2)).isoformat(),
            }
            if c.get("result") == "passed":
                row["silver_snapshot"] = silver_snapshot_before(silver_runs, _ml_ready_started(s3, c))
            rows.append(row)
        out[src] = rows
    return out


# ---------------------------------------------------------------------------
# 본문
# ---------------------------------------------------------------------------


def _md(iso: str) -> str:
    return iso[5:]


def build_message(sources: dict, as_of: date) -> tuple[str, str]:
    lines = [
        "계약 검사를 통과한 스냅샷입니다. 학습은 [최신]을 쓰세요. 확정 범위는 첫날 ~ 실행일-2일입니다.",
        "",
    ]
    subject_parts = []
    examples = []
    for src, cfg in SOURCES.items():
        rows = sources.get(src, [])
        passed = [r for r in rows if r["result"] == "passed"]
        lines.append(f"■ {cfg['label']} ({cfg['silver']} / {cfg['ml_ready'].split('.')[1]}){cfg['note']}")
        today = next((r for r in rows if r["run_date"] == as_of.isoformat()), None)
        if today is None:
            lines.append("  오늘 새 스냅샷 없음: 실행 없음")
        elif today["result"] != "passed":
            lines.append(f"  오늘 새 스냅샷 없음: 검사 {today['result']}")
        if not passed:
            lines.append(f"  최근 {LOOKBACK_DAYS}일 통과한 스냅샷 없음 — 운영자 확인 필요")
            subject_parts.append(f"{cfg['label'].split()[0]} 없음")
            lines.append("")
            continue
        for i, r in enumerate(passed[:SHOW]):
            tag = "[최신] " if i == 0 else "[이전] "
            lines.append(f"  {tag}{_md(r['run_date'])} 실행 · 확정 {_md(r['confirmed_from'])} ~ {_md(r['confirmed_to'])}")
            lines.append(f"         Silver   {r['silver_snapshot'] if r['silver_snapshot'] is not None else '(기록 없음)'}")
            lines.append(f"         ML-ready {r['ml_ready_snapshot']}")
        latest = passed[0]
        subject_parts.append(f"{cfg['label'].split()[0]} 확정 ~{_md(latest['confirmed_to'])}")
        end = (date.fromisoformat(latest["confirmed_to"]) + timedelta(days=1)).isoformat()
        examples.append(
            f"  SELECT * FROM {cfg['ml_ready']} FOR VERSION AS OF {latest['ml_ready_snapshot']} "
            f"WHERE measured_at >= TIMESTAMP '{latest['confirmed_from']} 00:00:00' AND measured_at < TIMESTAMP '{end} 00:00:00'"
        )
        lines.append("")
    if examples:
        lines += ["읽기 예시 (Athena · awswrangler)", *examples, ""]
    lines.append("자세히: specs/a-platform/008-ktms-silver-pipeline/contracts/ktms-tables.md")
    subject = f"[tms] 학습 스냅샷 {as_of.isoformat()} · " + " · ".join(subject_parts)
    return subject[:100], "\n".join(lines)


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def run(event: dict, s3, publish, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    as_of = date.fromisoformat(event["as_of"]) if event.get("as_of") else (now.astimezone(UTC) + KST).date()
    sources = collect(s3, as_of)
    subject, body = build_message(sources, as_of)
    published = False
    if not event.get("dry_run"):
        publish(subject, body)
        published = True
    return {"subject": subject, "body": body, "sources": sources, "published": published}


def handler(event, context=None):
    import boto3

    s3 = boto3.client("s3", region_name=REGION)
    sns = boto3.client("sns", region_name=REGION)

    def publish(subject: str, body: str) -> None:
        sns.publish(TopicArn=TOPIC_ARN, Subject=subject, Message=body)

    out = run(event or {}, s3, publish)
    print(json.dumps({"subject": out["subject"], "published": out["published"],
                      "counts": {k: len(v) for k, v in out["sources"].items()}}, ensure_ascii=False))
    return out
