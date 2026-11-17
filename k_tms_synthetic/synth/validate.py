'''
- validate: 만들어진 파일을 다시 읽어 합격 기준 검사
'''
import gzip
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from synth import compare

ITEM_NAMES = ["nox", "sox", "tsp", "hcl", "co", "nh3", "hf"]    # 실측과 같은 성분 7종
# 실측 항목의 18개 필드
REAL_FIELDS = {"area_nm", "fact_manage_nm", "stack_code", "mesure_dt"} | {f"{name}_{kind}" for name in ITEM_NAMES for kind in {"mesure_value", "exhst_perm_stdr_value"}}
# 값 칸에 허용하는 상태 문구 5종
STATUS_TEXTS = {"측정자료확인중(가동중지)", "측정자료확인중", "미수신", "보수중", "기기점검"}
VALUE_RE = re.compile(r"^\d+\.\d{2}$")                      # 측정값: 소수 둘째 자리
COMMA_RE = re.compile(r"^\d{1,3}(,\d{3})+\.\d$")           # 콤마가 포함된 숫자
LIMIT_RE = re.compile(r"^\d+(\.\d+)?$")                     # 허용 기준: 숫자 문자열
DATE_RE = re.compile(r"^ingest_date=(\d{4}-\d{2}-\d{2})$")  # 경로의 폴더 이름 형식
HOUR_RE = re.compile(r"^hour=(\d{2})$")
RUN_RE = re.compile(r"^run_ts=(\d{8}T\d{6}Z)$")

# 문제 한 개 목록에 추가
def _add(issues, episode_id, check, detail):
    issues.append({"episode_id": episode_id, "check": check, "detail": detail})

# 바이트의 SHA-256 해시
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

# out/manifest.jsonl을 읽어 dict로 변환
def _load_manifest(out: Path, issues) -> dict:
    path = out / "manifest.jsonl"
    if not path.exists():
        _add(issues, "-", "count", "manifest.jsonl이 없음")
        return {}
    lines = [ln for ln in path.read_text(encoding = "utf-8").splitlines() if ln.strip()]
    return {row["episode_id"]: row for row in map(json.loads, lines)}

# snapshot 폴더의 경로 형식 확인
def _check_path(snap_dir: Path, out: Path, episode_id: str, issues) -> None:
    parts = snap_dir.relative_to(out).parts
    ok = len(parts) == 5 and parts[0] == "tms_synthetic" and parts[1] == f"episode={episode_id}"
    matches = [rx.match(p) for rx, p in zip((DATE_RE, HOUR_RE, RUN_RE), parts[2:])] if ok else []
    if not ok or not all(matches):
        _add(issues, episode_id, "path", f"경로 형식이 다름: {'/'.join(parts)}")
        return
    date, hour, run = (m.group(1) for m in matches)
    t = datetime.strptime(run, "%Y%m%dT%H%M%SZ")
    if t.strftime("%Y-%m-%d") != date or t.strftime("%H") != hour:
        _add(issues, episode_id, "path", f"ingest_date, hour가 run_ts와 다름: {snap_dir.name}")

# 항목(dict) 한 개 검사. 측정 시각 문자열을 돌려줌(없으면 None)
def _check_item(it, episode_id, label, row, issues):
    if not isinstance(it, dict) or set(it) != REAL_FIELDS:
        _add(issues, episode_id, "fields", f"{label}: 필드가 실측 18개와 다름")
        return None
    code, dt = it["stack_code"], it["mesure_dt"]
    if not isinstance(code, str) or not code.startswith("SYN-") or code not in row["stack_codes"]:
        _add(issues, episode_id, "syn_code", f"{label}: 굴뚝 코드 {code!r}")
    try:
        if datetime.strptime(dt, "%Y-%m-%d %H:%M").minute not in (0, 30):
            _add(issues, episode_id, "grid", f"{label}: 30분 격자가 아님 {dt}")
    except (TypeError, ValueError):
        _add(issues, episode_id, "grid", f"{label}: 시각 형식 오류 {dt!r}")
        dt = None
    for name in ITEM_NAMES:
        value, limit = it[f"{name}_mesure_value"], it[f"{name}_exhst_perm_stdr_value"]
        if (value is None) != (limit is None):
            _add(issues, episode_id, "pairing", f"{label}: {name} 값, 허용기준 한 쪽만 있음")
        ok_value = value is None or (isinstance(value, str) and (
            VALUE_RE.match(value) or COMMA_RE.match(value) or value in STATUS_TEXTS
        ))
        ok_limit = limit is None or (isinstance(limit, str) and LIMIT_RE.match(limit))
        if not ok_value or not ok_limit:
            _add(issues, episode_id, "format", f"{label}: {name} 형식 오류 value = {value!r} limit = {limit!r}")
    return dt

# snapshot 폴더 하나를 검사. 항목들의 측정 시각을 목록으로 불러오기
def _validate_snapshot(snap_dir, out, episode_id, row, seen, issues):
    label = snap_dir.name
    _check_path(snap_dir, out, episode_id, issues)
    for name in ("manifest.json", "_SUCCESS"):
        if not (snap_dir / name).exists():
            _add(issues, episode_id, "commit", f"{label}: {name} 없음")
    gz_path, meta_path = snap_dir / "snapshot.json.gz", snap_dir / "snapshot.meta.json"
    if not gz_path.exists() or not meta_path.exists():
        _add(issues, episode_id, "files", f"{label}: 원문 또는 meta 없음")
        return []
    try:
        raw = gzip.decompress(gz_path.read_bytes())
        snap = json.loads(raw)
        header, items = snap["response"]["header"], snap["response"]["body"]["items"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        _add(issues, episode_id, "structure", f"{label}: 원문 구조 오류 ({type(e).__name__})")
        return []
    meta = json.loads(meta_path.read_text(encoding = "utf-8"))

    if header.get("resultCode") != "0" or header.get("totalCount") != len(items):
        _add(issues, episode_id, "response", f"{label}: 결과 코드, 전체 건수 불일치")
    if not meta.get("inspect", {}).get("ok"):
        _add(issues, episode_id, "response", f"{label}: meta의 inspect가 ok가 아님")

    if _sha256(raw) != meta.get("sha256_raw"):
        _add(issues, episode_id, "hash", f"{label}: 원문 해시가 meta와 다름")
    mf_path = snap_dir / "manifest.json"
    if mf_path.exists():
        mf = json.loads(mf_path.read_text(encoding = "utf-8"))
        if mf.get("raw_sha256") != _sha256(raw):
            _add(issues, episode_id, "hash", f"{label}: 원문 해시가 manifest와 다름")
        for f in mf.get("files", []):
            target = snap_dir / f["name"]
            if not target.exists() or _sha256(target.read_bytes()) != f["sha256"]:
                _add(issues, episode_id, "hash", f"{label}: {f['name']} 해시가 manifest와 다름")

    dts, codes_in_snapshot = [], set()
    for it in items:
        dt = _check_item(it, episode_id, label, row, issues)
        if dt is None or not isinstance(it, dict):
            continue
        dts.append(dt)
        if it["stack_code"] in codes_in_snapshot:
            _add(issues, episode_id, "duplicate", f"{label}: {it['stack_code']} 중복")
        codes_in_snapshot.add(it["stack_code"])
        key = (it["stack_code"], dt)
        if key in seen and seen[key] != it:
            _add(issues, episode_id, "repeat_conflict", f"{label}: {key} 값이 snapshot마다 다름")
        seen.setdefault(key, it)
    return dts

# 에피소드 하나 검사
def _validate_episode(out, episode_id, row, issues):
    ep_dir = out / "tms_synthetic" / f"episode={episode_id}"
    if not ep_dir.is_dir():
        _add(issues, episode_id, "count", "에피소드 폴더가 없음")
        return
    snap_dirs = sorted(d for d in ep_dir.glob("*/*/*") if d.is_dir())
    if len(snap_dirs) != row["snapshots"]:
        _add(issues, episode_id, "count", f"스냅샷 수 {len(snap_dirs)} (manifest{row['snapshots']})")
    seen, all_dts = {}, []
    for d in snap_dirs:
        all_dts += _validate_snapshot(d, out, episode_id, row, seen, issues)
    if all_dts and (min(all_dts) != row["first_mesure_dt"] or max(all_dts) != row["last_mesure_dt"]):
        _add(issues, episode_id, "count", f"측정 시각 범위가 manifest와 다름: {min(all_dts)}~{max(all_dts)}")

# 결과 폴더 전체를 검사. 문제 목록을 돌려줌(빈 목록 = 통과)
def validate_out(out_dir, expected_dir = None) -> list:
    out, issues = Path(out_dir), []
    manifest = _load_manifest(out, issues)
    for child in out.iterdir():
        if child.name not in ("tms_synthetic", "manifest.jsonl"):
            _add(issues, "-", "path", f"out 아래 예상 밖 항목: {child.name}")
    for episode_id, row in manifest.items():
        _validate_episode(out, episode_id, row, issues)
    root = out / "tms_synthetic"
    if root.exists():
        for d in root.iterdir():
            if d.name.removeprefix("episode=") not in manifest:
                _add(issues, "-", "count", f"manifest에 없는 에피소드 폴더: {d.name}") 
    if expected_dir is not None:
        issues += compare.compare_all(out, expected_dir)
    return issues

# 점검 결과를 사람이 읽기 쉽게 출력
def print_report(issues, out_dir) -> None:
    out = Path(out_dir)
    by_episode = {}
    for i in issues:
        by_episode.setdefault(i["episode_id"], []).append(i)
    for episode_id in _load_manifest(out, []):
        n = len(by_episode.get(episode_id, []))
        print(f"통과: {episode_id}" if n == 0 else f"불일치: {episode_id} ({n}건)")
    for i in issues[:30]:
        print(f"[{i['check']}] {i['episode_id']}: {i['detail']}")
    if len(issues) > 30:
        print(f"...외 {len(issues) - 30}건")