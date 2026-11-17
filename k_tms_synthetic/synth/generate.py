'''
- generate: 설정에서 합성 snapshot 파일들을 만들어 out/ 아래에 씀
- 흐름: 설정 -> plan -> stats(참조 배출구 선택) -> 곡선(episode) -> schedule(snapshot 시각표) -> snapshot -> 쓰기(writer) -> manifest.jsonl
'''
import json
import numpy as np
from pathlib import Path
from synth import episode, plan, schedule, snapshot, stats, writer
from synth.scenarios import trajectory

IMPLEMENTED = {"S-01", "S-02", "S-03", "S-04"}      # 만들 수 있는 시나리오
RETURN_MAX = 90.0                     # 궤적 뒤 복귀 구간의 상한

# 참조 배출구 한 곳 선택
def pick_reference(ref_df, item_name: str, ref_cfg: dict, rng):
    rows = ref_df[ref_df["item"] == item_name.upper()]
    rows = stats.usable(rows, ref_cfg["min_valid"])
    rows = stats.filter_normal(rows, ref_cfg["normal"])
    return stats.pick_one(rows, rng)

# 에피소드의 궤적 설정 이름: 변형이 없다면 "S-02", 있다면 "S-03-OVER"
def trajectory_key(ep: dict) -> str:
    return ep["scenario_id"] if not ep["variant"] else f"{ep['scenario_id']}-{ep['variant']}"

# 시나리오의 참조 조건: 시나리오별 설정이 있으면 조건을 따라감, 없다면 default
def trajectory_cond(ep: dict, ref_cfg: dict) -> dict:
    conds = ref_cfg["trajectory"]
    return conds.get(ep["scenario_id"], conds["default"])

# 에피소드에 쓸 참조 배출구 선택. 
def pick_refs(ep: dict, config: dict, ref_df, rng) -> dict:
    ref_cfg = config["ref_selection"]
    traj = config.get("trajectories", {}).get(trajectory_key(ep))
    items = ep["items"]
    if traj is None:
        return {name: pick_reference(ref_df, name, ref_cfg, rng) for name in items}
    cond = trajectory_cond(ep, ref_cfg)
    if len(items) == 1:
        rows = stats.usable(ref_df[ref_df["item"] == items[0].upper()], ref_cfg["min_valid"])
        return {items[0]: stats.pick_one(stats.filter_trajectory(rows, traj[0], cond), rng)}
    rising = ep["rising"][0]
    other = [name for name in items if name != rising][0]
    pair = stats.pick_pair(ref_df, rising.upper(), traj[0], cond, ref_cfg["normal"], ref_cfg["min_valid"], rng)
    return {rising: pair["rising"], other: pair["other"]}

# 성분별 기준대비율 곡선 생성
def make_ratios(ep: dict, config: dict, refs: dict, rng) -> dict:
    run, ref_cfg = config["run"], config["ref_selection"]
    steps = run["episode_steps"]
    traj = config.get("trajectories", {}).get(trajectory_key(ep))
    ratios = {}
    for name in ep["items"]:
        ref = refs[name]
        if traj is not None and name in ep["rising"]:                        
            cond = trajectory_cond(ep, ref_cfg)
            bg_max = cond.get("background_max", cond["p99_max"])          
            ratios[name] = trajectory.inject(steps, traj, run["trajectory_start_step"],
                                             ref["mean"], ref["std"], ref["phi"], rng, bg_max, RETURN_MAX)
        else:                                                                
            ratios[name] = episode.normal_series(steps, ref["mean"], ref["std"], ref["phi"], rng,
                                                 hi = ref_cfg["normal"]["p99_max"])
    return ratios

# 에피소드 하나의 snapshot 파일들을 모두 생성
def generate_episode(ep: dict, config: dict, ref_df, out_dir) -> dict:
    run, rng = config["run"], np.random.default_rng(ep["seed"])
    steps, slot_min = run["episode_steps"], run["slot_min"]
    refs = pick_refs(ep, config, ref_df, rng)                               
    ratios = make_ratios(ep, config, refs, rng)                             
    slots = schedule.mesure_times(ep["start_kst"], steps, slot_min)
    code = ep["stack_codes"][0]
    info = {
        "scenario_id": ep["scenario_id"], "generator_version": run["generator_version"], "stats_version": run["stats_version"]
        }
    times = schedule.snapshot_times(ep["start_kst"], steps, run["snapshot_interval_min"], slot_min)
    for t in times:
        k = schedule.latest_slot_index(ep["start_kst"], t, slot_min)
        measures = {name: snapshot.ratio_to_measure(float(ratios[name][k]), float(refs[name]["perm_std"]))
                    for name in ep["items"]}                              
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
        "ref": [                                                             
            {"item": name, "fact_manage_nm": refs[name]["fact_manage_nm"], "stack_code": str(refs[name]["stack_code"]),
             "role": "rising" if name in ep["rising"] and config.get("trajectories", {}).get(trajectory_key(ep)) else "background"}
            for name in ep["items"]
        ],
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