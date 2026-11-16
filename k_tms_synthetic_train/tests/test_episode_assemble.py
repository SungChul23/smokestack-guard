'''
- episode assemble test: warmup + 모양 + 복귀를 조립한 에피소드가 길이, 위치, 모양, 재현성을 지키는지 확인
'''
from pathlib import Path
from synth_train import shapes
from synth_train.assemble import assemble_episode
import numpy as np
import pytest
import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "daily.yaml"
SHAPES = ["OTHER", "SPIKE", "EXCEED", "PLATEAU", "OVER", "GRADUAL"]
REF = {"mean": 45.0, "std": 8.0, "phi": 0.8}                    # 시험용 참조 굴뚝 통계

def load():
    with open(CONFIG, encoding = "utf-8") as f:
        return yaml.safe_load(f)

# 모양의 그룹(low/high)에 맞는 배경 상한
def args_for(cfg, shape):
    ranges = cfg["shape_ranges"][shape]
    bg = cfg["ref_selection"]["groups"][ranges["group"]]["background_max"]
    return ranges, cfg["episode"], bg

# 길이, 모양 구간 밖 90% 미만, 전체 판정이 의도한 모양 (100개)
@pytest.mark.parametrize("shape", SHAPES)
def test_assembled_matches_shape(shape):
    cfg = load()
    ranges, ep, bg = args_for(cfg, shape)
    rng = np.random.default_rng(3)
    for _ in range(100):
        curve, start, end = assemble_episode(shape, rng, ranges, REF, ep, bg)
        assert start == ep["warmup_steps"]
        assert len(curve) == end + ep["return_steps"]
        assert (curve[:start] < 90).all()          # 앞 정상 구간
        assert (curve[end:] < 90).all()            # 뒤 복귀 구간
        assert (curve >= 0).all()
        assert shapes.classify_shape((curve / 100).tolist()) == shape

# 같은 seed면 같은 에피소드
@pytest.mark.parametrize("shape", SHAPES)
def test_assemble_reproducible(shape):
    cfg = load()
    ranges, ep, bg = args_for(cfg, shape)
    a = assemble_episode(shape, np.random.default_rng(5), ranges, REF, ep, bg)
    b = assemble_episode(shape, np.random.default_rng(5), ranges, REF, ep, bg)
    assert np.array_equal(a[0], b[0]) and a[1:] == b[1:]