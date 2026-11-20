'''
- daily.yaml test: 설정 파일의 구조와 값의 기본 조건을 확인
'''
from pathlib import Path
import yaml

CONFIG = Path(__file__).parents[1] / "config" / "daily.yaml"
SHAPES = {"FALLING", "SPIKE", "EXCEED", "PLATEAU", "OVER", "GRADUAL",
          "NEAR_HOLD", "IRREGULAR_RISE", "OSCILLATION", "NEAR_MISS"}

def load():
    return yaml.safe_load(CONFIG.read_text(encoding = "utf-8"))

# 성분마다 6개의 모양, 에피소드 수는 0 이상의 정수
def test_daily_episodes_cover_all_shapes():
    cfg = load()["daily_episodes"]
    assert set(cfg) == {"nox", "sox"}
    for item, counts in cfg.items():
        assert set(counts) == SHAPES, item
        assert all(isinstance(n, int) and n >= 0 for n in counts.values()), item

# 모양별 범위는 [최소, 최대] 쌍, 최소 <= 최대
def test_shape_ranges_are_valid_pairs():
    ranges = load()["shape_ranges"]
    assert set(ranges) == SHAPES
    for shape, spec in ranges.items():
        for key, value in spec.items():
            if key == "group":
                continue
            assert len(value) == 2 and value[0] <= value[1], f"{shape}.{key}"

# 모든 모양의 group이 ref_selection.groups에 정의되어 있음
def test_shape_groups_are_defined():
    cfg = load()
    groups = set(cfg["ref_selection"]["groups"])
    assert {spec["group"] for spec in cfg["shape_ranges"].values()} <= groups

# 에피소드 앞 구간은 피쳐가 보는 6칸 이상
def test_warmup_covers_feature_window():
    assert load()["episode"]["warmup_steps"] >= 6

# 합성 run_ts 규칙과 격자
def test_snapshot_rules():
    snap = load()["snapshot"]
    assert snap["slot_min"] == 30
    assert snap["run_ts_offset_min"] == 70   

# 하루 양성 행 = 에피소드 수 x 2 : 실측 적격 양성과 1:1 수준
def test_daily_positives_match_real():
    eps = load()["daily_episodes"]
    def positives(c):
        return sum(n * (5 if s == "OVER" else 2) for s, n in c.items())
    assert 245 <= positives(eps["nox"]) <= 275
    assert 75 <= positives(eps["sox"]) <= 95

# 중간형 양성이 근접형보다 많아야 함
def test_mid_positives_exceed_near():
    eps = load()["daily_episodes"]["nox"]
    mid = {"FALLING": 1.69, "NEAR_HOLD": 0.41, "IRREGULAR_RISE": 1.63, "OSCILLATION": 0.97,
           "SPIKE": 0.66, "EXCEED": 1.64, "PLATEAU": 1.71, "OVER": 0.09, "GRADUAL": 0.71}
    near = {"FALLING": 0.31, "NEAR_HOLD": 1.59, "IRREGULAR_RISE": 0.37, "OSCILLATION": 1.02,
            "SPIKE": 0.0, "EXCEED": 0.36, "PLATEAU": 0.28, "OVER": 4.92, "GRADUAL": 1.29}
    assert sum(eps[s] * mid.get(s, 0) for s in eps) > 1.3 * sum(eps[s] * near.get(s, 0) for s in eps)

# 생성기 버전 
def test_generator_version_is_v2():
    assert load()["run"]["generator_version"] == "gen-train-v2"