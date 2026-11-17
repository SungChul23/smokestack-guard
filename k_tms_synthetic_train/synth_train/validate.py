'''
- validate: 생성된 학습용 합성 Bronze 폴더 점검
'''
import gzip
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from synth_train import schedule, shapes, snapshot

ITEM_NAMES = snapshot.ITEMS
REAL_FIELDS = {"area_nm", "fact_manage_nm", "stack_code", "mesure_dt"} | {
    f"{n}_{k}" for n in ITEM_NAMES for k in ("mesure_value", "exhst_perm_stdr_value")}
VALUE_RE = re.compile(r"^\d+\.\d{2}$")                           # 측정값: 소수 둘째 자리
LIMIT_RE = re.compile(r"^\d+(\.\d+)?$")                          # 허용기준: 숫자 문자열
STACK_RE = re.compile(r"^SYN-T-\d{8}-(NOX|SOX)-[A-Z]+-\d{3}$")   # 합성 굴뚝 코드
DATE_RE = re.compile(r"^ingest_date=(\d{4}-\d{2}-\d{2})$")
HOUR_RE = re.compile(r"^hour=(\d{2})$")
RUN_RE = re.compile(r"^run_ts=(\d{8}T\d{6}Z)$")
MESURE_FMT = "%Y-%m-%d %H:%M"
SLOTS_PER_DAY = 48

def _add(issues, check, detail):
    issues.append({"check": check, "detail": detail})

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

# 폴더 경로 형식
def _check_path(d: Path, out: Path, issues):
    parts = d.relative_to(out).parts
    ok = len(parts) == 4 and parts[0] == snapshot.TRAIN_ROOT
    matches = [rx.match(p) for rx, p in zip((DATE_RE, HOUR_RE, RUN_RE), parts[1:])] if ok else []
    if not ok or not all(matches):
        _add(issues, "path", f"경로 형식이 다름: {'/'.join(parts)}")
        return None
    date, hour, run = (m.group(1) for m in matches)
    t = datetime.strptime(run, "%Y%m%dT%H%M%SZ").replace(tzinfo = timezone.utc)
    if t.strftime("%Y-%m-%d") != date or t.strftime("%H") != hour:
        _add(issues, "path", f"ingest_date, hour가 run_ts와 다름: {d.name}")
    return t

# 항목 한 개: 필드 18개, 합성 코드, 30분 격자, 값 형식
def _check_item(it, label, issues):
    if not isinstance(it, dict) or set(it) != REAL_FIELDS:
        _add(issues, "fields", f"{label}: 필드가 실측 18개와 다름")
        return False
    code = it["stack_code"]
    if not isinstance(code, str) or not STACK_RE.match(code):
        _add(issues, "syn_code", f"{label}: 합성 굴뚝 코드 형식이 아님 {code!r}")
    try:
        if datetime.strptime(it["mesure_dt"], MESURE_FMT).minute not in (0, 30):
            _add(issues, "grid", f"{label}: 30분 격자가 아님 {it['mesure_dt']}")
    except (TypeError, ValueError):
        _add(issues, "grid", f"{label}: 시각 형식 오류 {it['mesure_dt']!r}")
    for name in ITEM_NAMES:
        value, limit = it[f"{name}_mesure_value"], it[f"{name}_exhst_perm_stdr_value"]
        if (value is None) != (limit is None):
            _add(issues, "pairing", f"{label}: {name} 값, 허용기준 한 쪽만 있음")
        ok_value = value is None or (isinstance(value, str) and VALUE_RE.match(value))
        ok_limit = limit is None or (isinstance(limit, str) and LIMIT_RE.match(limit))
        if not ok_value or not ok_limit:
            _add(issues, "format", f"{label}: {name} 형식 오류 value={value!r} limit={limit!r}")
    return True

# snapshot 폴더 하나를 돌려줌. 읽을 수 없다면 None
def _validate_snapshot(d: Path, out: Path, issues):
    label = d.name
    run_utc = _check_path(d, out, issues)
    for name in ("manifest.json", "_SUCCESS"):
        if not (d / name).exists():
            _add(issues, "commit", f"{label}: {name} 없음")
    gz, meta_path = d / "snapshot.json.gz", d / "snapshot.meta.json"
    if not gz.exists() or not meta_path.exists():
        _add(issues, "files", f"{label}: 원문 또는 meta 없음")
        return None
    try:
        raw = gzip.decompress(gz.read_bytes())
        snap = json.loads(raw)
        header, items = snap["response"]["header"], snap["response"]["body"]["items"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        _add(issues, "structure", f"{label}: 원문 구조 오류 ({type(e).__name__})")
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    if header.get("resultCode") != "0" or header.get("totalCount") != len(items):
        _add(issues, "response", f"{label}: 결과 코드, 전체 건수 불일치")
    if _sha256(raw) != meta.get("sha256_raw"):
        _add(issues, "hash", f"{label}: 원문 해시가 meta와 다름")
    mf_path = d / "manifest.json"
    if mf_path.exists():
        mf = json.loads(mf_path.read_text(encoding="utf-8"))
        if mf.get("raw_sha256") != _sha256(raw):
            _add(issues, "hash", f"{label}: 원문 해시가 manifest와 다름")
        for f in mf.get("files", []):
            target = d / f["name"]
            if not target.exists() or _sha256(target.read_bytes()) != f["sha256"]:
                _add(issues, "hash", f"{label}: {f['name']} 해시가 manifest와 다름")
    return run_utc, items

# 항목 기준 대비율 복원, 구하지 못하면 None
def _ratio(it, item_name):
    try:
        return float(it[f"{item_name}_mesure_value"]) / float(it[f"{item_name}_exhst_perm_stdr_value"]) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return None

def _load_manifest_rows(out: Path) -> list:
    rows = []
    for p in sorted((out / "manifest").glob("*.jsonl")):
        rows += [json.loads(x) for x in p.read_text(encoding = "utf-8").splitlines() if x.strip()]
    return rows

# 폴더 전체 점검. 문제 목록 반환
def validate_out(out_dir, real_codes = frozenset(), offset_min: int = 70) -> list:
    out, issues = Path(out_dir), []
    for child in out.iterdir():
        if child.name not in (snapshot.TRAIN_ROOT, "manifest"):
            _add(issues, "path", f"out 아래 예상 밖 항목: {child.name}")

    slots = {}          # KST 날짜 -> 그날 슬롯 시각 목록
    by_stack = {}       # 굴뚝 코드 -> {측정 시각: 항목}
    seen = set()
    root = out / snapshot.TRAIN_ROOT
    for d in sorted(root.glob("ingest_date=*/hour=*/run_ts=*")) if root.exists() else []:
        if not d.is_dir():
            continue
        got = _validate_snapshot(d, out, issues)
        if got is None or got[0] is None:
            continue
        run_utc, items = got
        slot_kst = (run_utc - timedelta(minutes=offset_min)).astimezone(schedule.KST)
        slot_text = slot_kst.strftime(MESURE_FMT)
        slots.setdefault(slot_kst.date(), []).append(slot_text)
        for it in items:
            if not _check_item(it, d.name, issues):
                continue
            if it["mesure_dt"] != slot_text:
                _add(issues, "slot_time", f"{d.name}: 측정 시각 {it['mesure_dt']}가 슬롯 {slot_text}와 다름")
            if it["stack_code"] in real_codes:
                _add(issues, "syn_collision", f"{it['stack_code']}가 실측 굴뚝 코드와 같음")
            key = (it["stack_code"], it["mesure_dt"])
            if key in seen:
                _add(issues, "duplicate", f"{d.name}: {key} 중복")
            seen.add(key)
            by_stack.setdefault(it["stack_code"], {})[it["mesure_dt"]] = it

    for day, texts in sorted(slots.items()):
        if len(texts) != SLOTS_PER_DAY or len(set(texts)) != SLOTS_PER_DAY:
            _add(issues, "slots", f"{day}: 슬롯 {len(set(texts))}종 / 스냅샷 {len(texts)}개 (기대 {SLOTS_PER_DAY})")

    # manifest의 에피소드마다: 이어짐, 모양 (데이터 끝을 넘어가는 에피소드는 건너뜀)
    data_end = max((t for texts in slots.values() for t in texts), default=None)
    for row in _load_manifest_rows(out):
        if data_end is not None and row["last_mesure_dt"] > data_end:
            continue
        first = datetime.strptime(row["first_mesure_dt"], MESURE_FMT)
        want = [(first + timedelta(minutes=30 * i)).strftime(MESURE_FMT) for i in range(row["snapshots"])]
        got = by_stack.get(row["stack_code"], {})
        if sorted(got) != want:
            _add(issues, "continuity", f"{row['stack_code']}: 측정 시각이 끊기거나 어긋남 (기대 {len(want)}칸, 실제 {len(got)}칸)")
            continue
        ratios = [_ratio(got[t], row["item"]) for t in want]
        if None in ratios:
            continue
        try:
            got_shape = shapes.classify_shape([r / 100 for r in ratios])
        except ValueError:                                
            _add(issues, "shape", f"{row['stack_code']}: 사건이 둘 이상이라 모양을 정할 수 없음")
            continue
        if got_shape != row["shape"]:
            _add(issues, "shape", f"{row['stack_code']}: 모양이 manifest({row['shape']})와 다름")
    return issues

# 점검 결과를 사람이 읽기 쉽게 출력
def print_report(issues) -> None:
    print("통과" if not issues else f"불일치 {len(issues)}건")
    for i in issues[:30]:
        print(f"[{i['check']}] {i['detail']}")
