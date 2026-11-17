'''
- generate: 날짜 하나의 합성 데이터를 Bronze 모양 파일로 생성
'''
import json
from datetime import timedelta
from pathlib import Path
from synth_train import daily, pack, schedule, snapshot, writer

# manifest 한 줄 
def manifest_row(config: dict, ep: dict) -> dict:
    run = config["run"]
    first = daily.midnight(ep["day"]) + timedelta(minutes = 30 * ep["start_slot"])
    last = first + timedelta(minutes = 30 * (len(ep["curve"]) - 1))
    return {
        "day": f"{ep['day']:%Y-%m-%d}",
        "item": ep["item"], "shape": ep["shape"], "n": ep["n"],
        "stack_code": ep["stack_code"],
        "ref": {"fact_manage_nm": ep["ref"]["fact_manage_nm"], "stack_code": ep["ref"]["stack_code"]},
        "seed": ep["seed"], "start_slot": ep["start_slot"],
        "first_mesure_dt": schedule.format_mesure_dt(first),
        "last_mesure_dt": schedule.format_mesure_dt(last),
        "snapshots": len(ep["curve"]),
        "rows": len(ep["curve"]),                         
        "stats_version": run["stats_version"],
        "generator_version": run["generator_version"],
    }

# 날짜(KST) 하나를 쓴다. 전날 자정분도 seed로 다시 만들어 섞음
def generate_day(config: dict, ref_df, day, out_dir) -> dict:
    prev = daily.episodes_started_on(config, ref_df, day - timedelta(days = 1))
    cur = daily.episodes_started_on(config, ref_df, day)
    snaps = pack.pack_day(config, prev + cur, day)

    info = {"generator_version": config["run"]["generator_version"],
            "stats_version": config["run"]["stats_version"]}
    for s in snaps:
        files = snapshot.make_files(s["snapshot"], "", s["run_ts"], info, snapshot.TRAIN_ROOT)
        prefix = snapshot.build_prefix("", s["run_ts"], snapshot.TRAIN_ROOT)
        writer.write_files(out_dir, prefix, files)

    rows = [manifest_row(config, ep) for ep in cur]
    out = Path(out_dir) / "manifest"
    out.mkdir(parents = True, exist_ok = True)
    lines = [json.dumps(r, ensure_ascii = False, sort_keys = True) for r in rows]
    (out / f"{day:%Y-%m-%d}.jsonl").write_text("\n".join(lines) + "\n", encoding = "utf-8", newline = "")
    return {"day": f"{day:%Y-%m-%d}", "snapshots": len(snaps), "rows": sum(s["rows"] for s in snaps), "episodes": len(rows)}

# 백필
def backfill(config: dict, ref_df, start, end, out_dir) -> list:
    results = []
    day = start
    while day <= end:
        results.append(generate_day(config, ref_df, day, out_dir))
        day += timedelta(days = 1)
    return results