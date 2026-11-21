'''
- lambda_handler test: AWS 적재 진입점 (spec 011). 가짜 S3로 슬롯 고르기, 건너뛰기, 백필, 점검을 확인
'''
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

import pytest

import lambda_handler as lh
from synth_train import generate, snapshot, writer

BUCKET = "raw"
KST = timezone(timedelta(hours = 9))
D = date(2026, 11, 16)


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.order = []

    def put_object(self, Bucket, Key, Body, **kw):
        self.objects[Key] = bytes(Body)
        self.order.append(Key)

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def list_objects_v2(self, Bucket, Prefix, MaxKeys = 1000):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))[:MaxKeys]
        return {"Contents": [{"Key": k} for k in keys]} if keys else {}


@pytest.fixture(scope = "module")
def local_day(config, ref_df, tmp_path_factory):
    '''파일 모드(generate-day)로 같은 날짜를 로컬에 쓴 결과'''
    out = tmp_path_factory.mktemp("local")
    generate.generate_day(config, ref_df, D, out)
    return out


def run(event, s3, config, ref_df, now, publish = None):
    return lh.run(event, s3, BUCKET, config, lambda: ref_df, publish, now = now)


def run_ts_keys(s3):
    return sorted({k.split("/")[3] for k in s3.objects if "/run_ts=" in k})


# ---------------------------------------------------------------------------
# 정기 실행 (US1)
# ---------------------------------------------------------------------------

def test_regular_writes_only_the_due_slot(config, ref_df):
    s3 = FakeS3()
    now = datetime(2026, 11, 16, 10, 10, tzinfo = KST)
    out = run({"mode": "regular", "scheduled_time": now.isoformat()}, s3, config, ref_df, now,)
    # 180분 창 (07:10, 10:10] 안의 도착 시각 6개. 측정 09:00 슬롯 = 10:10 KST = 01:10 UTC
    assert out["written"][-1] == "20261116T011000Z"
    assert len(out["written"]) == 6
    prefix = snapshot.build_prefix("", datetime(2026, 11, 16, 1, 10, tzinfo = timezone.utc), snapshot.TRAIN_ROOT)
    keys = [k for k in s3.order if k.startswith(prefix)]
    assert [k.rsplit("/", 1)[1] for k in keys] == ["snapshot.json.gz", "snapshot.meta.json", "manifest.json", "_SUCCESS"]
    assert out["manifest_written"] == ["2026-11-16"]


def test_regular_skips_committed_and_fills_gaps(config, ref_df):
    s3 = FakeS3()
    first = datetime(2026, 11, 16, 9, 40, tzinfo = KST)
    run({"mode": "regular", "scheduled_time": first.isoformat()}, s3, config, ref_df, first)
    before = dict(s3.objects)
    # 10:10 실행은 빠지고 10:40 실행: 10:10·10:40 두 슬롯을 쓰고 나머지는 건너뜀
    later = datetime(2026, 11, 16, 10, 40, tzinfo = KST)
    out = run({"mode": "regular", "scheduled_time": later.isoformat()}, s3, config, ref_df, later)
    assert out["written"] == ["20261116T011000Z", "20261116T014000Z"]
    assert out["skipped"] == 4 and out["manifest_written"] == []
    assert all(s3.objects[k] == v for k, v in before.items())  # 확정 폴더는 그대로


def test_regular_across_midnight_writes_previous_day_slots(config, ref_df):
    s3 = FakeS3()
    now = datetime(2026, 11, 17, 0, 10, tzinfo = KST)  # 측정 23:00(전날) 슬롯 도착
    out = run({"mode": "regular", "scheduled_time": now.isoformat()}, s3, config, ref_df, now)
    assert out["written"][-1] == "20261116T151000Z"
    body = json.loads(__import__("gzip").decompress(s3.objects[[k for k in s3.objects if k.endswith("151000Z/snapshot.json.gz")][0]]))
    assert {it["mesure_dt"] for it in body["response"]["body"]["items"]} == {"2026-11-16 23:00"}


def test_bytes_match_file_mode(config, ref_df, local_day):
    s3 = FakeS3()
    run({"mode": "backfill", "from": "2026-11-16", "to": "2026-11-16"}, s3, config, ref_df,
        datetime(2026, 11, 18, tzinfo = KST))
    local = {str(p.relative_to(local_day)).replace("\\", "/"): p.read_bytes()
             for p in local_day.rglob("*") if p.is_file() and "/run_ts=" in str(p).replace("\\", "/")}
    remote = {k: v for k, v in s3.objects.items() if "/run_ts=" in k}
    assert len(remote) == 48 * 4
    assert set(local) == set(remote)
    assert all(hashlib.sha256(local[k]).digest() == hashlib.sha256(remote[k]).digest() for k in local)
    manifest = (local_day / "manifest" / "2026-11-16.jsonl").read_bytes()
    assert s3.objects[f"{lh.MANIFEST_PREFIX}/2026-11-16.jsonl"] == manifest
    # v2 경로에만 쓴다 (spec 015, B의 v2는 tms_synthetic_train_v2/)
    assert lh.TRAIN_ROOT == "tms_synthetic_train_v2"
    assert all(k.startswith("tms_synthetic_train_v2/") for k in s3.objects)


def test_no_kafka_imports_and_real_path_rejected():
    # 다른 테스트가 같은 프로세스에서 publish 등을 불러올 수 있어 새 프로세스로 확인한다
    code = ("import sys, lambda_handler; "
            "bad = {'confluent_kafka', 'yaml', 'synth_train.publish', 'synth_train.release', 'synth_train.cycle', "
            "'synth_train.plan'} & set(sys.modules); print(sorted(bad)); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], cwd = Path(lh.__file__).parent, capture_output = True, text = True)
    assert r.returncode == 0, r.stdout + r.stderr
    with pytest.raises(ValueError):
        writer.check_prefix("tms_cleansys/ingest_date=2026-11-16/hour=01/run_ts=20261116T011000Z")


# ---------------------------------------------------------------------------
# 백필 (US3)
# ---------------------------------------------------------------------------

def test_backfill_two_days_skips_existing_and_future(config, ref_df):
    s3 = FakeS3()
    now = datetime(2026, 11, 17, 10, 10, tzinfo = KST)
    run({"mode": "regular", "scheduled_time": now.isoformat()}, s3, config, ref_df, now)
    out = run({"mode": "backfill", "from": "2026-11-16", "to": "2026-11-17"}, s3, config, ref_df, now)
    assert out["skipped"] == 6
    # 11-16: 48개, 11-17: 도착 시각이 10:10 이하인 슬롯(01:10~10:10 = 19개)
    assert len(run_ts_keys(s3)) == 48 + 19
    assert out["manifest_written"] == ["2026-11-16"]


@pytest.mark.parametrize("event", [
    {"mode": "backfill", "from": "2026-10-01", "to": "2026-11-16"},
    {"mode": "backfill", "from": "2026-11-17", "to": "2026-11-16"},
    {"mode": "backfill", "from": "bad", "to": "2026-11-16"},
    {"mode": "train"},
    {"mode": "regular", "scheduled_time": "2026-11-16T10:10:00"},
])
def test_bad_inputs_fail_before_writing(config, ref_df, event):
    s3 = FakeS3()
    with pytest.raises(ValueError):
        run(event, s3, config, ref_df, datetime(2026, 11, 18, tzinfo = KST))
    assert s3.objects == {}


# ---------------------------------------------------------------------------
# 점검·재처리 (US2)
# ---------------------------------------------------------------------------

def test_check_reports_missing_slots(config, ref_df):
    s3 = FakeS3()
    run({"mode": "backfill", "from": "2026-11-16", "to": "2026-11-16"}, s3, config, ref_df,
        datetime(2026, 11, 18, tzinfo = KST))
    gone = [k for k in s3.objects if k.endswith("_SUCCESS")][:2]
    for k in gone:
        del s3.objects[k]
    sent = []
    out = run({"mode": "check", "day": "2026-11-16"}, s3, config, ref_df, datetime(2026, 11, 17, 6, tzinfo = KST),
              publish = lambda s, b: sent.append((s, b)))
    assert len(out["missing"]) == 2 and out["expected"] == 48
    subject, body = sent[0]
    assert subject.isascii() and subject == "[tms] synthetic train missing slots - 2026-11-16 (46/48)"
    assert all(m in body for m in out["missing"]) and '"mode": "backfill"' in body


def test_check_defaults_to_yesterday_and_is_quiet_when_complete(config, ref_df):
    s3 = FakeS3()
    run({"mode": "backfill", "from": "2026-11-16", "to": "2026-11-16"}, s3, config, ref_df,
        datetime(2026, 11, 18, tzinfo = KST))
    sent = []
    out = run({"mode": "check"}, s3, config, ref_df, datetime(2026, 11, 17, 6, tzinfo = KST),
              publish = lambda s, b: sent.append(s))
    assert out["window"] == ["2026-11-16", "2026-11-16"] and out["missing"] == [] and sent == []


def test_dlq_bodies_unwrap_to_the_same_input():
    now = datetime(2026, 11, 18, tzinfo = KST)
    original = {"mode": "regular", "scheduled_time": "2026-11-16T01:10:00Z"}
    wrapped = {"requestContext": {"condition": "RetriesExhausted"}, "requestPayload": original,
               "responsePayload": {"errorMessage": "x"}}
    assert lh.parse_event(original, now) == lh.parse_event(wrapped, now)


# ---------------------------------------------------------------------------
# 설정·참조 통계
# ---------------------------------------------------------------------------

def test_ref_stats_version_must_match(config, ref_df, tmp_path):
    s3 = FakeS3()
    good = ref_df.assign(stats_version = config["run"]["stats_version"])
    s3.objects[lh.ref_key(config)] = good.to_csv(index = False).encode("utf-8")
    assert len(lh.load_ref(s3, BUCKET, config, tmp = tmp_path)) == len(good)
    other = tmp_path / "other"
    other.mkdir()
    s3.objects[lh.ref_key(config)] = ref_df.to_csv(index = False).encode("utf-8")  # stats_version = test
    with pytest.raises(ValueError, match = "버전"):
        lh.load_ref(s3, BUCKET, config, tmp = other)


def test_json_config_wins_over_yaml(tmp_path, config):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "daily.json").write_text(json.dumps(config), encoding = "utf-8")
    assert lh.load_config(tmp_path) == config


def _terraform_json(value):
    '''Terraform의 jsonencode(yamldecode(...))처럼: 정수 값 실수(2.0)는 정수(2)가 된다'''
    if isinstance(value, dict):
        return {k: _terraform_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_terraform_json(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def test_terraform_json_config_gives_same_bytes(config, ref_df):
    converted = json.loads(json.dumps(_terraform_json(config)))
    a, b = FakeS3(), FakeS3()
    now = datetime(2026, 11, 18, tzinfo = KST)
    event = {"mode": "backfill", "from": "2026-11-16", "to": "2026-11-16"}
    run(event, a, config, ref_df, now)
    run(event, b, converted, ref_df, now)
    assert a.objects == b.objects


def test_terraform_zip_module_list_is_enough_to_import(tmp_path):
    '''infra/stacks/tms-synthetic/main.tf의 zip 목록 파일만 복사한 폴더에서 진입점이 import되는지 (Lambda와 같은 조건)'''
    import re
    import shutil
    root = Path(lh.__file__).parent
    tf = (root.parent / "infra" / "stacks" / "tms-synthetic" / "main.tf").read_text(encoding = "utf-8")
    block = re.search(r"modules = \[(.*?)\]", tf, re.S).group(1)
    files = re.findall(r'"(synth_train/[^"]+\.py)"', block)
    assert files
    for f in files + ["lambda_handler.py"]:
        (tmp_path / f).parent.mkdir(parents = True, exist_ok = True)
        shutil.copy(root / f, tmp_path / f)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "daily.json").write_text("{}", encoding = "utf-8")
    code = "import lambda_handler, synth_train.daily, synth_train.pack, synth_train.generate, synth_train.s3_sink"
    r = subprocess.run([sys.executable, "-c", code], cwd = tmp_path, capture_output = True, text = True)
    assert r.returncode == 0, r.stderr


def test_unsubstituted_scheduler_placeholder_uses_run_time(config, ref_df):
    '''Scheduler가 <aws.scheduler.scheduled-time>을 그대로 넘겨도 실행 시각 기준으로 쓴다 (2026-11-17 운영)'''
    now = datetime(2026, 11, 17, 17, 40, 46, tzinfo = KST)
    raw = {"mode": "regular", "scheduled_time": "<aws.scheduler.scheduled-time>"}
    assert lh.parse_event(raw, now)["now"] == now
    s3 = FakeS3()
    out = run(raw, s3, config, ref_df, now)
    assert out["written"][-1] == "20261117T084000Z"

