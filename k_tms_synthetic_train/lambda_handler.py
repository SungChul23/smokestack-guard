"""학습용 합성 데이터 AWS 적재 Lambda 진입점 (spec: specs/a-platform/011-synthetic-train-s3-ingest).

- 생성 규칙은 synth_train을 수정 없이 쓴다. 이 파일은 "어느 슬롯을 쓸지"와 S3·알림만 다룬다.
- 에피소드는 저장하지 않는다. 슬롯이 속한 날짜 D의 스냅샷 48개를 전날+당일 에피소드로 다시 계산하고
  쓸 슬롯만 고른다(research R2).
- 쓰기는 s3_sink.write_files_s3(데이터 → 해시 확인 → manifest → _SUCCESS). _SUCCESS가 있으면 건너뛴다.
- Kafka(publish·release·cycle)는 import하지 않는다.

입력(contracts/ingest-interface.md §1):
  {"mode": "regular", "scheduled_time": "<ISO>"}   정기, 최근 180분 안의 빈 슬롯
  {"mode": "backfill", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}   날짜별 48슬롯 (31일 이내)
  {"mode": "check", "day": "YYYY-MM-DD"}   전날(기본) 48슬롯 점검, 모자라면 SNS
  DLQ 메시지 본문(원래 입력, 또는 requestPayload로 감싼 것)
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from synth_train import daily, generate, pack, s3_sink, schedule, snapshot, stats

ROOT = Path(__file__).resolve().parent
TRAIN_ROOT = snapshot.TRAIN_ROOT
MANIFEST_PREFIX = f"{TRAIN_ROOT}/_manifest"
REF_PREFIX = f"{TRAIN_ROOT}/_ref_stats"
MODES = ("regular", "backfill", "check")
MAX_BACKFILL_DAYS = 31
DEFAULT_LOOKBACK_MIN = 180
DOC = "specs/a-platform/011-synthetic-train-s3-ingest/contracts/ingest-interface.md"

_CACHE: dict = {}

# ---------------------------------------------------------------------------
# 설정·참조 통계
# ---------------------------------------------------------------------------


def load_config(root: Path = ROOT) -> dict:
    """배포 zip에는 Terraform이 만든 config/daily.json이 있다(research R3). 로컬은 yaml."""
    js = root / "config" / "daily.json"
    if js.exists():
        return json.loads(js.read_text(encoding="utf-8"))
    from synth_train import plan

    return plan.load_config(root / "config" / "daily.yaml")


def ref_key(config: dict) -> str:
    return f"{REF_PREFIX}/{config['run']['stats_version']}.csv"


def load_ref(s3, bucket: str, config: dict, tmp: Path = Path("/tmp")):
    """참조 통계를 S3에서 받아 읽는다. 파일 안 stats_version이 설정과 다르면 쓰기 전에 실패한다(R7)."""
    want = config["run"]["stats_version"]
    path = tmp / f"ref_stats_{want}.csv"
    if not path.exists():
        body = s3.get_object(Bucket=bucket, Key=ref_key(config))["Body"].read()
        path.write_bytes(body)
    df = stats.load_ref_stats(path)
    versions = set(df["stats_version"].dropna().astype(str)) if "stats_version" in df else set()
    if versions != {want}:
        raise ValueError(f"참조 통계 버전이 설정({want})과 다르다: {sorted(versions)}")
    return df


# ---------------------------------------------------------------------------
# 입력
# ---------------------------------------------------------------------------


def _day(value, name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{name}는 YYYY-MM-DD여야 한다: {value!r}") from exc


def _time(value) -> datetime:
    t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError(f"scheduled_time에는 시간대가 있어야 한다: {value!r}")
    return t.astimezone(UTC)


def parse_event(event: dict | None, now: datetime) -> dict:
    """data-model §2. DLQ 본문(Lambda 실패 목적지는 requestPayload로 감쌈)도 받는다."""
    event = dict(event or {})
    if isinstance(event.get("requestPayload"), dict):
        event = dict(event["requestPayload"])
    mode = event.get("mode") or "regular"
    if mode not in MODES:
        raise ValueError(f"mode는 {MODES} 중 하나여야 한다: {mode!r}")
    p: dict = {"mode": mode}
    if mode == "regular":
        # Scheduler가 자리표시자(<aws.scheduler.scheduled-time>)를 치환하지 않고 그대로 넘기는 경우가 있다
        # (2026-11-17 운영 확인). 값이 없거나 자리표시자면 실행 시각을 쓴다. 예정 시각과 몇 초 차이다.
        sched = str(event.get("scheduled_time") or "")
        p["now"] = _time(sched) if sched and not sched.startswith("<") else now
        p["lookback_min"] = int(event.get("lookback_min") or DEFAULT_LOOKBACK_MIN)
    elif mode == "backfill":
        start, end = _day(event.get("from"), "from"), _day(event.get("to"), "to")
        if start > end:
            raise ValueError(f"from({start})이 to({end})보다 늦다")
        if (end - start).days + 1 > MAX_BACKFILL_DAYS:
            raise ValueError(f"백필은 한 번에 {MAX_BACKFILL_DAYS}일까지다: {start}~{end}")
        p |= {"from": start, "to": end, "now": now}
    else:
        default = (now.astimezone(schedule.KST) - timedelta(days=1)).date()
        p["day"] = _day(event["day"], "day") if event.get("day") else default
    return p


# ---------------------------------------------------------------------------
# 스냅샷 계산과 쓰기
# ---------------------------------------------------------------------------


def day_snapshots(config: dict, ref_df, day: date, cache: dict | None = None) -> list:
    """날짜 D(KST)의 48슬롯 스냅샷. 전날 시작한 에피소드도 넣는다(자정을 넘는 에피소드)."""
    cache = {} if cache is None else cache
    if day not in cache:
        eps = daily.episodes_started_on(config, ref_df, day - timedelta(days=1))
        eps += daily.episodes_started_on(config, ref_df, day)
        cache[day] = pack.pack_day(config, eps, day)
    return cache[day]


def offset(config: dict) -> timedelta:
    return timedelta(minutes=config["snapshot"]["run_ts_offset_min"])


def exists(s3, bucket: str, key: str) -> bool:
    """키가 있는지. head_object는 목록 권한 없이는 없는 키에 403을 주므로,
    접두어 조건을 걸 수 있는 list_objects_v2로 확인한다(research R6)."""
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1)
    return any(o["Key"] == key for o in resp.get("Contents", []))


def committed(s3, bucket: str, prefix: str) -> bool:
    return exists(s3, bucket, f"{prefix}/_SUCCESS")


def info(config: dict) -> dict:
    run = config["run"]
    return {"generator_version": run["generator_version"], "stats_version": run["stats_version"]}


def write_slot(s3, bucket: str, config: dict, slot: dict) -> bool:
    """확정 표지가 없으면 쓰고 True. 있으면 건너뛰고 False(007 규칙)."""
    prefix = snapshot.build_prefix("", slot["run_ts"], TRAIN_ROOT)
    if committed(s3, bucket, prefix):
        return False
    files = snapshot.make_files(slot["snapshot"], "", slot["run_ts"], info(config), TRAIN_ROOT)
    s3_sink.write_files_s3(s3, bucket, prefix, files)
    return True


def write_manifest(s3, bucket: str, config: dict, ref_df, day: date) -> bool:
    """에피소드 태그 _manifest/D.jsonl(시작 날짜가 D인 에피소드). 이미 있으면 건너뛴다."""
    key = f"{MANIFEST_PREFIX}/{day:%Y-%m-%d}.jsonl"
    if exists(s3, bucket, key):
        return False
    rows = [generate.manifest_row(config, ep) for ep in daily.episodes_started_on(config, ref_df, day)]
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body)
    return True


def due_days(now: datetime, lookback_min: int, off: timedelta) -> list[date]:
    """run_ts가 (now − lookback, now]인 슬롯이 속할 수 있는 측정 날짜(KST)."""
    lo = (now - timedelta(minutes=lookback_min) - off).astimezone(schedule.KST).date()
    hi = (now - off).astimezone(schedule.KST).date()
    return sorted({lo, hi})


def run_regular(p: dict, s3, bucket: str, config: dict, ref_df) -> dict:
    now, lookback = p["now"], p["lookback_min"]
    lo = now - timedelta(minutes=lookback)
    written, skipped, manifests, cache = [], 0, [], {}
    for day in due_days(now, lookback, offset(config)):
        slots = [s for s in day_snapshots(config, ref_df, day, cache) if lo < s["run_ts"] <= now]
        for slot in slots:
            if write_slot(s3, bucket, config, slot):
                written.append(f"{slot['run_ts']:%Y%m%dT%H%M%SZ}")
            else:
                skipped += 1
        if slots and write_manifest(s3, bucket, config, ref_df, day):
            manifests.append(f"{day:%Y-%m-%d}")
    return {"window": [lo.isoformat(), now.isoformat()], "written": written,
            "skipped": skipped, "manifest_written": manifests}  # fmt: skip


def run_backfill(p: dict, s3, bucket: str, config: dict, ref_df) -> dict:
    written, skipped, manifests, cache = [], 0, [], {}
    day = p["from"]
    while day <= p["to"]:
        for slot in day_snapshots(config, ref_df, day, cache):
            if slot["run_ts"] > p["now"]:
                continue  # 아직 도착할 때가 아님
            if write_slot(s3, bucket, config, slot):
                written.append(f"{slot['run_ts']:%Y%m%dT%H%M%SZ}")
            else:
                skipped += 1
        if write_manifest(s3, bucket, config, ref_df, day):
            manifests.append(f"{day:%Y-%m-%d}")
        cache.pop(day - timedelta(days=1), None)
        day += timedelta(days=1)
    return {"window": [f"{p['from']}", f"{p['to']}"], "written": written,
            "skipped": skipped, "manifest_written": manifests}  # fmt: skip


def expected_prefixes(config: dict, day: date) -> list[str]:
    """날짜 D의 48슬롯 폴더 경로. 에피소드 계산 없이 시각만으로 정해진다."""
    base = daily.midnight(day)
    slot_min = config["snapshot"]["slot_min"]
    return [
        snapshot.build_prefix("", schedule.to_run_ts(base + timedelta(minutes=slot_min * s) + offset(config)), TRAIN_ROOT)
        for s in range(daily.SLOTS_PER_DAY)
    ]


def check_alert(day: date, missing: list[str], total: int) -> tuple[str, str]:
    have = total - len(missing)
    subject = f"[tms] synthetic train missing slots - {day:%Y-%m-%d} ({have}/{total})"
    payload = json.dumps({"mode": "backfill", "from": f"{day}", "to": f"{day}"})
    body = "\n".join([
        f"학습용 합성 데이터: {day:%Y-%m-%d}(KST) 슬롯 {total}개 중 {len(missing)}개에 확정 표지가 없다.",
        "",
        "빈 슬롯(run_ts, UTC):",
        *[f"  {m}" for m in missing],
        "",
        "다시 채우기: aws lambda invoke --region ap-northeast-2 --function-name tms-synthetic-train "
        f"--cli-binary-format raw-in-base64-out --payload '{payload}' /dev/stdout",
        "이틀 넘게 지났다면 그 날짜로 합성 매일 갱신도 다시 실행한다.",
        f"읽는 법: {DOC}",
    ])  # fmt: skip
    return subject, body


def run_check(p: dict, s3, bucket: str, config: dict, publish=None) -> dict:
    day = p["day"]
    prefixes = expected_prefixes(config, day)
    missing = [pre.rsplit("run_ts=", 1)[1] for pre in prefixes if not committed(s3, bucket, pre)]
    if missing and publish is not None:
        subject, body = check_alert(day, missing, len(prefixes))
        publish(subject, body)
    return {"window": [f"{day}", f"{day}"], "missing": missing, "expected": len(prefixes)}


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def run(event: dict, s3, bucket: str, config: dict, ref_loader, publish=None, now=None) -> dict:
    p = parse_event(event, now or datetime.now(UTC))
    if p["mode"] == "check":
        out = run_check(p, s3, bucket, config, publish)
    else:
        ref_df = ref_loader()
        fn = run_regular if p["mode"] == "regular" else run_backfill
        out = fn(p, s3, bucket, config, ref_df)
    out = {"mode": p["mode"], **out} | info(config)
    summary = {k: (len(v) if isinstance(v, list) and k != "window" else v) for k, v in out.items()}
    print(json.dumps(summary, ensure_ascii=False, default=str))
    return out


def handler(event, context):
    import boto3

    bucket = os.environ["BUCKET"]
    topic = os.environ.get("ALERT_TOPIC_ARN")
    s3 = boto3.client("s3")
    if "config" not in _CACHE:
        _CACHE["config"] = load_config()
    config = _CACHE["config"]

    def ref_loader():
        if "ref" not in _CACHE:
            _CACHE["ref"] = load_ref(s3, bucket, config)
        return _CACHE["ref"]

    def publish(subject: str, body: str) -> None:
        if topic:
            boto3.client("sns").publish(TopicArn=topic, Subject=subject, Message=body)

    return run(event, s3, bucket, config, ref_loader, publish)
