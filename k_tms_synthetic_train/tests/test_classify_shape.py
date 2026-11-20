'''
- classify_shape test: 고정 궤적이 기대한 모양으로 판정되고, 경계와 우선순위 규칙이 지켜지는지 확인
'''
import pytest
from synth_train import shapes

# 궤적을 정상 배경 사이에 끼운 시계열. 앞 12칸은 사건 전, 뒤 8칸은 사건 후
def episode_with(traj_pct, lead = 0.5, n_lead = 12, n_tail = 8):
    return [lead] * n_lead + [p / 100 for p in traj_pct] + [0.5] * n_tail

# 고정 궤적 5개 + 어디에도 안 맞는 궤적
@pytest.mark.parametrize("traj, want", [
    ([56, 58, 113, 109, 104, 71, 60], "EXCEED"),
    ([59, 61, 92, 95, 93, 96, 94, 70, 62], "PLATEAU"),
    ([87, 91, 88, 92, 89, 91], "OVER"),               
    ([59, 61, 94, 63, 60], "SPIKE"),                     
    ([62, 69, 76, 82, 87, 92], "GRADUAL"),                     
    ([80, 78, 85, 92, 70], "OTHER"),                      
])
def test_fixed_trajectories(traj, want):
    assert shapes.classify_shape(episode_with(traj)) == want

# 판정 우선순위 100% 이상 3칸이면서 경계를 3칸 넘나들어도 EXCEED가 먼저
def test_exceed_has_priorty_over_over():
    assert shapes.classify_shape(episode_with([95, 105, 85, 110, 85, 120])) == "EXCEED"

# GRADUAL은 직전 값 4칸이 모두 있어야 함
def test_gradual_needs_four_valid_values():
    series = episode_with([62, 69, 76, 82, 87, 92])
    i = 12 + 2
    series[i] = None
    assert shapes.classify_shape(series) == "OTHER"

# 사건이 시계열 앞쪽이라 직전 값이 업스염ㄴ SPIKE도 GRADUAL도 아님
def test_event_at_start_has_no_history():
    assert shapes.classify_shape([0.95] + [0.5] * 5) == "OTHER"

# 경계: 정확히 90%, 90%이상 행
def test_high_boundary_is_inclusive():
    assert shapes.classify_shape([0.5, 0.5, 0.90, 0.5]) == "SPIKE"
    assert shapes.classify_shape([0.5, 0.5, 0.8999, 0.5]) is None

# 경계: SPILE는 전이 70% 미만이여야 함
def test_spike_boundary():
    assert shapes.classify_shape([0.5, 0.5, 0.70, 0.94, 0.6]) == "OTHER"

# 사건이 없으면 None
def test_no_event():
    assert shapes.classify_shape([0.5] * 10) is None

# 사건이 둘 이상이면 모양을 하나로 못 정해 오류
def test_two_events_raise():
    with pytest.raises(ValueError):
        shapes.classify_shape([0.95, 0.5, 0.5, 0.5, 0.95])

# 60분 안에 다시 진입하면 같은 사건, 진입은 2번 
def test_reentry_within_60minutes_is_same_event():
    events = shapes.find_events([0.5, 0.95, 0.5, 0.95, 0.5])
    assert len(events) == 1
    assert events[0]["entries"] == 2
    assert events[0]["rows"] == [1, 3]

# 기본값은 기존 판정(OTHER), detail = True면 진입 전 모양으로 나뉨
def test_classify_shape_detail_splits_other():
    ratios = [0.5] * 8 + [0.84, 0.85, 0.84, 0.86] + [0.95] + [0.5] * 4
    assert shapes.classify_shape(ratios) == "OTHER"
    assert shapes.classify_shape(ratios, detail = True) == "NEAR_HOLD"

# 사건이 없거나 둘 이상일 때의 규칙은 detail = True에서도 같음
def test_classify_shape_detail_keeps_event_rules():
    assert shapes.classify_shape([0.5] * 10, detail = True) is None
    with pytest.raises(ValueError):
        shapes.classify_shape([0.95, 0.5, 0.5, 0.5, 0.95], detail = True)

# 사건이 없고 최고값 80~90%면 detail = True에서 NEAR_MISS, 기본은 None
def test_classify_shape_detail_near_miss():
    series = [0.5, 0.7, 0.85, 0.88, 0.75, 0.5]
    assert shapes.classify_shape(series) is None
    assert shapes.classify_shape(series, detail = True) == "NEAR_MISS"

# 최고값이 80% 미만이면 사건이 없어도 NEAR_MISS가 아님
def test_classify_shape_detail_float_is_none():
    assert shapes.classify_shape([0.5, 0.6, 0.7, 0.6], detail = True) is None
    