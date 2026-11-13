'''
- compare: 생성 결과를 expected/*.yaml과 대조
'''
import gzip
import json
import yaml
from pathlib import Path

ITEMS = {"nox", "sox"}

def _add(issues, episode_id, check, detail):
    issues.append({"episode_id": episode_id, "check": check, "detail": detail})

# 에피소드의 성분별 기준대비율 목록
def read_ratios(out, episode_id) -> dict:
    seen = {}
    for gz in sorted((Path(out) / "tms_synthetic" / f"episode={episode_id}").glob("*/*/*/snapshot.json.gz")):
        for it in json.loads(gzip.decompress(gz.read_bytes()))["response"]["body"]["items"]:
            for name in ITEMS:
                value, limit = it[f"{name}_mesure_value"], it[f"{name}_exhst_perm_stdr_value"]
                if value is None or limit is None:
                    continue
                try:
                    seen[(name, it["mesure_dt"])] = float(value) / float(limit)
                except ValueError:
                    continue

    ratios = {}
    for (name, _), r in sorted(seen.items()):
        ratios.setdefault(name, []).append(r)
    return ratios

# 에피소드 하나를 expected(dict)와 대조
def compare_episode(out, exp: dict) -> list:
    eid, issues = exp["episode_id"], []
    ratios = read_ratios(out, eid)
    start = exp.get("trajectory_start_step")
    traj = [p / 100 for p in exp["trajectory_pct"]] if exp.get("trajectory_pct") else None
    for name, spec in exp["silver_expect"].items():
        r = ratios.get(name, [])
        if len(r) != spec["rows"]: 
            _add(issues, eid, "rows", f"{name}: 행 수 {len(r)} (expected {spec['rows']})")
            continue
        has_traj = traj is not None and name in exp["rising"]
        first = (start - 1) if has_traj else len(r)
        end = first + len(traj) if has_traj else len(r)
        if has_traj:
            tol = spec["trajectory_ratio_tol"]
            for i, want in enumerate(traj):
                if abs(r[first + i] - want) > tol:
                    _add(issues, eid, "trajectory", f"{name}: {start + i}번째 칸 {r[first + i]:.3f} (expected {want})")
        outside = r[:first] + r[end:] 
        for key, values, check in (
            ("ratio_max_exclusive", r, "max"), 
            ("ratio_max_exclusive_outside", outside, "outside"),
            ("lead_in_max_exclusive", r[:first], "lead_in"),
        ):
            if key in spec and values and max(values) >= spec[key]:
                _add(issues, eid, check, f"{name}: 최댓값 {max(values):.3f} (상한 {spec[key]} 미만이어야 함)")
    return issues

# out/manifest.jsonl의 모든 에피소드를 expected 폴더와 대조
def compare_all(out, expected_dir) -> list:
    issues = []
    manifest = Path(out) / "manifest.jsonl"
    ids = [json.loads(ln)["episode_id"] for ln in manifest.read_text(encoding = "utf-8").splitlines() if ln.strip()]
    for eid in ids:
        path = Path(expected_dir) / f"{eid}.yaml"
        if not path.exists():
            _add(issues, eid, "expected", f"expected 파일이 없음: {path.name}")
            continue
        issues += compare_episode(out, yaml.safe_load(path.read_text(encoding = "utf-8")))
    return issues
