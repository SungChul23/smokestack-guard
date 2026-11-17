'''
- pick_pair test: NOX + SOX 에피소드가 같은 굴뚝의 NOX, SOX 한 쌍을 고르는지 확인
'''
import numpy as np
import pandas as pd
import pytest
from synth import stats

TRAJ = {"p99_max": 70, "first_value_within_sigma": 2.0}            
NORMAL = {"mean": [10, 50], "phi": [0.5, 0.95], "p99_max": 70}

# 통계 표의 한 줄 만들기
def row(item, name, mean, std, p99, comp, phi = 0.8):
    return {"item": item, "fact_manage_nm": name, "stack_code": 1, "n_valid": 300,
            "mean": mean, "std": std, "phi": phi, "p50": mean, "p99": p99, "max_pct": p99,
            "perm_std": 100, "perm_distinct": 1, "items_measured": comp, "stats_version": "provisional"
            }

# 같은 굴뚝의 NOX, SOX가 모두 조건에 맞으면 그 쌍을 고름. 다른 굴뚝의 미끼를 고르지 않음
def test_pair_is_same_stack_with_both_items():
    df = pd.DataFrame([
        row("NOX", "굴뚝X", 60, 8, 65, "NOX+SOX"),
        row("SOX", "굴뚝X", 20, 5, 40, "NOX+SOX"),
        row("NOX", "굴뚝Y", 60, 8, 65, "NOX"),
        row("NOX", "굴뚝Z", 60, 8, 65, "NOX+SOX"),
        row("SOX", "굴뚝Z", 20, 5, 90, "NOX+SOX"),
    ])
    pair = stats.pick_pair(df, "NOX", 62, TRAJ, NORMAL, 200, np.random.default_rng(0))
    assert pair["rising"]["item"] == "NOX" and pair["other"]["item"] == "SOX"
    assert pair["rising"]["fact_manage_nm"] == "굴뚝X"
    assert pair["other"]["fact_manage_nm"] == "굴뚝X"

# SOX가 오르는 경우 역할이 바뀜
def test_pair_when_sox_rises():
    df = pd.DataFrame([row("SOX", "굴뚞W", 60, 8, 65, "NOX+SOX"),
                       row("NOX", "굴뚞W", 20, 5, 40, "NOX+SOX")])
    pair = stats.pick_pair(df, "SOX", 62, TRAJ, NORMAL, 200, np.random.default_rng(0))
    assert pair["rising"]["item"] == "SOX" and pair["other"]["item"] == "NOX"

# 조건에 맞는 쌍이 없다면 에러
def test_pair_raises_when_no_pair():
    df = pd.DataFrame([row("NOX", "굴뚝Y", 60, 8, 65, "NOX")])
    with pytest.raises(ValueError):
        stats.pick_pair(df, "NOX", 62, TRAJ, NORMAL, 200, np.random.default_rng(0))

# 같은 seed면 같은 굴뚝을 고름
def test_pair_is_reproducible():
    df = pd.DataFrame([
        row("NOX", "굴뚝A", 60, 8, 65, "NOX+SOX"), row("SOX", "굴뚝A", 20, 5, 40, "NOX+SOX"),
        row("NOX", "굴뚝B", 58, 8, 66, "NOX+SOX"), row("SOX", "굴뚝B", 25, 5, 45, "NOX+SOX"),
    ])
    a = stats.pick_pair(df, "NOX", 62, TRAJ, NORMAL, 200, np.random.default_rng(5))
    b = stats.pick_pair(df, "NOX", 62, TRAJ, NORMAL, 200, np.random.default_rng(5))
    assert a["rising"]["fact_manage_nm"] == b["rising"]["fact_manage_nm"]