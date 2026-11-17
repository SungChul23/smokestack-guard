'''
- validate test: 정상 출력은 통과하고, 일부러 규칙을 어긴 출력은 걸리는지 확인
'''
import gzip
import json
import shutil
import pytest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from synth_train import generate, schedule, snapshot, validate

D1 = date(2026, 11, 16)
D2 = date(2026, 11, 17)

# 정상 출력. 테스트마다 복사해서 망가뜨림
@pytest.fixture(scope = "module")
def clean_out(config, ref_df, tmp_path_factory):
    out = tmp_path_factory.mktemp("clean")
    generate.backfill(config, ref_df, D1, D2, out)
    return out

@pytest.fixture
def out(clean_out, tmp_path):
    dst = tmp_path / "out"
    shutil.copytree(clean_out, dst)
    return dst

def checks(issues):
    return {i["check"] for i in issues}

def run_dirs(out):
    return sorted(p for p in (out / "tms_synthetic_train").glob("ingest_date=*/hour=*/run_ts=*") if p.is_dir())

def manifest_rows(out, day):
    lines = (out / "manifest" / f"{day:%Y-%m-%d}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines]

# 스냅샷 원문을 고쳐 씀
def edit_snapshot(run_dir, fn):
    p = run_dir / "snapshot.json.gz"
    snap = json.loads(gzip.decompress(p.read_bytes()))
    fn(snap)
    raw = json.dumps(snap, ensure_ascii=False, separators = (",", ":")).encode("utf-8")
    p.write_bytes(gzip.compress(raw, mtime = 0))

def test_clean_output_passes(out):
    assert validate.validate_out(out) == []

def test_syn_code_collision(out):
    code = manifest_rows(out, D1)[0]["stack_code"]
    assert "syn_collision" in checks(validate.validate_out(out, real_codes = {code}))

# 슬롯이 48개가 아니라면 거름
def test_day_slots(out):
    shutil.rmtree(run_dirs(out)[30])
    assert "slots" in checks(validate.validate_out(out))

# 곡선이 manifest의 모양과 다르면 걸림
def test_shape_mismatch(out):
    path = out / "manifest" / "2026-11-16.jsonl"
    rows = manifest_rows(out, D1)
    row = next(r for r in rows if r["shape"] == "SPIKE")
    row["shape"] = "OVER"
    path.write_text("\n".join(json.dumps(r, ensure_ascii = False, sort_keys = True) for r in rows)
                     + "\n", encoding = "utf-8", newline = "")
    assert "shape" in checks(validate.validate_out(out))

# 자정을 걸친 에피소드의 다음 날 슬롯이 사라지면 걸림
def test_spill_continuity(out):
    run_ts = (datetime(2026, 11, 17, 0, 0, tzinfo = schedule.KST) + 
              timedelta(minutes = 70)).astimezone(timezone.utc)
    shutil.rmtree(out / snapshot.build_prefix("", run_ts, snapshot.TRAIN_ROOT))
    assert "continuity" in checks(validate.validate_out(out))

# 값에 숫자가 아닌 문자열이 있으면 걸림
def test_non_numeric_value(out):
    def corrupt(snap):
        it = snap["response"]["body"]["items"][0]
        key = next(k for k in it if k.endswith("_mesure_value") and it[k] is not None)
        it[key] = "abc"
    edit_snapshot(run_dirs(out)[24], corrupt)
    assert "format" in checks(validate.validate_out(out))

# 중복 항목이면 걸림
def test_duplicate_item(out):
    def corrupt(snap):
        items = snap["response"]["body"]["items"]
        items.append(dict(items[0]))
        snap["response"]["header"]["totalCount"] = len(items)
    edit_snapshot(run_dirs(out)[24], corrupt)
    assert "duplicate" in checks(validate.validate_out(out))