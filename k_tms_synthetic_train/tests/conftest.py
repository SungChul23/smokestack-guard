'''
- conftest: 테스트 공용 준비물
'''
from pathlib import Path
import pandas as pd
import pytest
import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "daily.yaml"

# 성분마다 평균 20~65, 표준편차 5~12인 굴뚝 40곳
@pytest.fixture(scope = "session")
def ref_df():
    rows = []
    for item in ["NOX", "SOX"]:
        for k in range(40):
            mean = 20 + (k % 10) * 5
            std = 5 + (k % 4) * 2.5
            rows.append({
                "item": item, "fact_manage_nm": f"시험사업장{k}", "stack_code": str(k),
                "n_valid": 1000, "mean": float(mean), "std": float(std), "phi": 0.8,
                "p50": float(mean), "p99": mean + 2.5 * std, "max_pct": mean + 3 * std,
                "perm_std": 100.0, "perm_distinct": 1, "items_measured": item,
                "stats_version": "test",
            })
    return pd.DataFrame(rows)

@pytest.fixture(scope = "session")
def config():
    with open(CONFIG, encoding = "utf-8") as f:
        return yaml.safe_load(f)