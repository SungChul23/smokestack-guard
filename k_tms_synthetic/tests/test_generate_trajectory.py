'''
- generate(궤적 시나리오) test: 설정의 궤적이 정해진 칸에 들어가고, NOX+SOX는 한 행에 두 성분이 담기는지 확인
'''
import gzip
import json
import numpy as np
import pandas as pd
from synth import generate
from tests.test_generate import FIXTURE
from tests.test_pick_pair import row

S02 = [62, 69, 76, 82, 87, 92]

# 궤적 시나리오용 테스트 설정 (측정 96칸, 궤적은 48번째 칸부터)
def traj_config(episodes, trajectories):
    return {
        "run": {"seed": 1, "generator_version": "gen-v1", "stats_version": "provisional",
                "snapshot_interval_min": 10, "slot_min": 30, "episode_steps": 96,
                "start_kst": "2026-11-20 09:00", "trajectory_start_step": 48},
        "ref_selection": {
            "min_valid": 200,
            "normal": {"mean": [10, 50], "phi": [0.5, 0.95], "p99_max": 70},
            "trajectory": {"default": {"p99_max": 80, "background_max": 70, "first_value_within_sigma": 2.0}},
        },
        "episodes": episodes,
        "trajectories": trajectories,
    }

# 에피소드의 모든 스냅샷에서 (측정 시각 -> 기준대비율)을 모아 시간순 목록으로
def read_ratios(out, episode_id, item):
    seen = {}
    for gz in (out / "tms_synthetic" / f"episode={episode_id}").glob("*/*/*/snapshot.json.gz"):
        it = json.loads(gzip.decompress(gz.read_bytes()))["response"]["body"]["items"][0]
        seen[it["mesure_dt"]] = float(it[f"{item}_mesure_value"]) / float(it[f"{item}_exhst_perm_stdr_value"])
    return [seen[k] for k in sorted(seen)]

# 궤적이 설정한 칸(48번째~)에 그대로 들어가고, 궤적 밖은 모두 90% 미만
def test_spike_trajectory_lands_on_expected_steps(tmp_path):
    cfg = traj_config({"S-04-E": {"variants": ["SPIKE"], "items": ["nox"]}}, {"S-04-SPIKE": [59, 61, 94, 63, 60]})
    generate.generate(cfg, FIXTURE, tmp_path)
    ratios = read_ratios(tmp_path, "S-04-E-SPIKE", "nox")
    assert len(ratios) == 96
    assert np.allclose(ratios[47:52], [0.59, 0.61, 0.94, 0.63, 0.60], atol = 0.005)
    assert max(ratios[:47] + ratios[52:]) < 0.90

# NOX+SOX 에피소드: 같은 굴뚝 한 행에 두 성분이 담기고, 오르는 성분(NOX)만 궤적을 따름
def test_noxsox_pair_in_one_row(tmp_path):
    csv = tmp_path / "ref.csv"
    pd.DataFrame([row("NOX", "굴뚝X", 58, 6, 66, "NOX+SOX", phi = 0.7),
                  row("SOX", "굴뚝X", 20, 5, 40, "NOX+SOX")]).to_csv(csv, index = False, encoding = "utf-8-sig")
    eps = {"S-02-E": {"episodes": [{"suffix": "NOXSOX-NOXUP", "items": ["nox", "sox"], "rising": ["nox"]}]}}
    out = tmp_path / "out"
    rows = generate.generate(traj_config(eps, {"S-02": S02}), csv, out)
    nox = read_ratios(out, "S-02-E-NOXSOX-NOXUP", "nox")          
    sox = read_ratios(out, "S-02-E-NOXSOX-NOXUP", "sox")
    assert np.allclose(nox[47:53], [r / 100 for r in S02], atol = 0.005)
    assert max(sox) < 0.70                                         
    assert {r["item"]: r["role"] for r in rows[0]["ref"]} == {"nox": "rising", "sox": "background"}