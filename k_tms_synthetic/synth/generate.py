'''
- generate: 설정에서 합성 snapshot 파일들을 만들어 out/ 아래에 씀
- 흐름: 설정 -> plan -> stats(참조 배출구 선택) -> 곡선(episode) -> schedule(snapshot 시각표) -> snapshot -> 쓰기(writer) -> manifest.jsonl
'''
import json
import numpy as np
from pathlib import Path
from synth import episode, plan, schedule, snapshot, stats, writer

IMPLEMENTED = {"S-01"}      # 만들 수 있는 시나리오

# 참조 배출구 한 곳 선택
def pick_reference(ref_df, item_name: str, ref_cfg: dict, rng):
    rows = ref_df[ref_df["item"] == item_name.upper()]
    rows = stats.usable(rows, ref_cfg["min_valid"])
    rows = stats.filter_normal(rows, ref_cfg["normal"])
    return stats.pick_one(rows, rng)

# 에피소드 하나의 snapshot 파일들을 모두 만들어 씀
def generate_episode(ep: dict, config: dict, ref_df, out_dir) -> dict:
    run, rng = config["run"], np.random.default_rng(ep["seed"])
    steps, slot_min = run["episode_steps"], run["slot_min"]
    name = ep["items"][0]
    ref = pick_reference(ref_df, name, config["ref_selection"], rng)
    hi = config["ref_selection"]["normal"]["p99_max"]       # 배경 상한: 참조 조건의 p99 상한과 같게 (S-01은 70%)
    ratios = episode.normal_series(steps, ref["mean"], ref["std"], ref["phi"], rng, hi = hi)
    slots = schedule.mesure_times(ep["start_kst"], steps, slot_min)
    code = ep["stack_codes"][0]
    info = {
        "scenario_id": ep["scenario_id"], "generator_version": run["generator_version"], "stats_version": run["stats_version"]
        }
    times = schedule.snapshot_times(ep["start_kst"], steps, run["snapshot_interval_min"], slot_min)
    for t in times:
        k = schedule.latest_slot_index(ep["start_kst"], t, slot_min)
        measures = {name: snapshot.ratio_to_measure(float(ratios[k]), float(ref["perm_std"]))}
        item = snapshot.make_item(
            "합성지역", code.replace("SYN-", "합성사업장-"), code, schedule.format_mesure_dt(slots[k]), measures,
        )
        run_ts = schedule.to_run_ts(t)
        files = snapshot.make_files(snapshot.make_snapshot([item]), ep["episode_id"], run_ts, info)
        writer.write_files(out_dir, snapshot.build_prefix(ep["episode_id"], run_ts), files)
    return {
        "episode_id": ep["episode_id"], 
        "scenario_id": ep["scenario_id"], 
        "stack_codes": ep["stack_codes"], 
        "ref": {
            "fact_manage_nm": ref["fact_manage_nm"], 
            "stack_code": str(ref["stack_code"]), 
            "item": ref["item"]
            },
        "ref_stats_version": run["stats_version"], 
        "generator_version": run["generator_version"],
        "seed": ep["seed"], 
        "first_mesure_dt": schedule.format_mesure_dt(slots[0]),
        "last_mesure_dt": schedule.format_mesure_dt(slots[-1]),
        "snapshots": len(times),
    }

# 설정 전체 실행
def generate(config: dict, stats_path, out_dir) -> list:
    ref_df = stats.load_ref_stats(stats_path)
    rows = []
    for ep in plan.build_plan(config):
        if ep["scenario_id"] not in IMPLEMENTED:
            print(f"건너뜀(미구현): {ep['episode_id']}")
            continue
        rows.append(generate_episode(ep, config, ref_df, out_dir))
        print(f"생성: {ep['episode_id']} ({rows[-1]['snapshots']}개)")

    out = Path(out_dir)
    out.mkdir(parents = True, exist_ok = True)
    lines = [json.dumps(r, ensure_ascii = False, sort_keys = True) for r in rows]
    (out / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding = "utf-8", newline = "")
    return rows