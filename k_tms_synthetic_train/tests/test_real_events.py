import pandas as pd
from synth_train import real_events

COLS = ["item", "fact_manage_nm", "stack_code", "mesure_dt", "ratio"]

# 작은 CSV를 만들어 주는 도우미
def write_csv(tmp_path, rows):
    p = tmp_path / "s.csv"
    pd.DataFrame(rows, columns = COLS).to_csv(p, index = False, encoding = "utf-8")
    return p

# 빈 칸은 None으로 채워지고, 격자 길이는 start-end의 30분 칸 수
def test_load_series_fills_missing_with_none(tmp_path):
    p = write_csv(tmp_path, [
        ["NOX", "A", 1, "2026-10-30 00:00", 0.5],
        ["NOX", "A", 1, "2026-10-30 01:00", 0.9],
    ])
    got = real_events.load_series(p, "2026-10-30 00:00", "2026-10-30 01:30")
    assert got[("NOX", "A", "1")] == [0.5, None, 0.9, None]

# 같은 stack_code라도 사업장이 다르면 다른 굴뚝
def test_load_seriesseparates_same_code_different_facility(tmp_path):
    p = write_csv(tmp_path, [
        ["NOX", "A", 1, "2026-10-30 00:00", 0.5],
        ["NOX", "B", 1, "2026-10-30 00:00", 0.6]
    ])
    got = real_events.load_series(p, "2026-10-30 00:00", "2026-10-30 00:30")
    assert len(got) == 2

# 직전 단서: 30분 또는 60분 전에 유요한 90% 미만 값이 있으면 True
def test_has_cue():
    ev = {"rows": [2], "entries": 1}
    assert real_events.has_cue([0.5, 0.6, 0.95], ev) is True
    assert real_events.has_cue([None, 0.5, 0.95], ev) is True                                       # 30분 전만 있어도 상관 없음
    assert real_events.has_cue([0.5, None, 0.95], ev) is True                                       # 60분 전만 있어도 상관 없음
    assert real_events.has_cue([None, None, 0.95], ev) is False                                     # 둘 다 없음
    assert real_events.has_cue([0.95, 0.95, 0.95], {"rows": [0, 1, 2], "entries": 1}) is False

# 사건 추출: SPIKE, OTHER(단서 있음), OTHER(단서 없음)
def test_extract_events_shape_and_cue():
    other = [0.5] * 8 + [0.8, 0.95] + [0.5] * 8
    no_cue = [0.95, 0.95, 0.95] + [0.5] * 6
    gradual = [0.5] * 12 + [0.55, 0.62, 0.70, 0.78, 0.85, 0.95] + [0.5] * 8
    assert [(e["shape"], e["cue"]) for e in real_events.extract_events(other)] == [("OTHER", True)]
    assert [(e["shape"], e["cue"]) for e in real_events.extract_events(no_cue)] == [("OTHER", False)]
    assert [(e["shape"], e["cue"]) for e in real_events.extract_events(gradual)] == [("GRADUAL", True)]

# curve는 진입 4칸 전부터 2칸 뒤까지 7칸, 범위 밖은 None
def test_extract_events_curve_window():
    ratios = [0.5, 0.95, 0.5, 0.5]
    ev = real_events.extract_events(ratios)[0]
    assert ev["curve"] == [None, None, None, 0.5, 0.95, 0.5, 0.5]

# 사건 특징: 90% 이상 칸 수, 최고값, 진입 횟수, 복귀 값
def test_extract_events_features():
    ev = real_events.extract_events([0.5] * 8 + [0.8, 0.95] + [0.5] * 8)[0]
    assert ev["high_rows"] == 1
    assert ev['peak'] == 0.95
    assert ev["entries"] == 1
    assert ev["after"] == 0.5

# 90% 이상이 3칸 이어지면 high_rows 3, 최고값은 그중 가장 큰 값
def test_extract_events_features_multi_rows():
    ev = real_events.extract_events([0.6] * 4 + [0.92, 0.97, 0.91] + [0.6] * 3)[0]
    assert ev["high_rows"] == 3
    assert ev["peak"] == 0.97
    assert ev["after"] == 0.6

# 90% 이상 사이에 한 칸 내려갔다 오르면 같은 사건, 진입 2회
def test_extract_events_features_two_entries():
    ev = real_events.extract_events([0.6] * 4 + [0.95, 0.6, 0.95] + [0.6] * 3)[0]
    assert ev["high_rows"] == 2
    assert ev["entries"] == 2

# 마지막 칸이 90% 이상이면 복귀 값 없음
def test_extract_events_after_none_at_end():
    ev = real_events.extract_events([0.5, 0.95])[0]
    assert ev["after"] is None 

# 세부 판정: OTHER가 진입 전 4칸으로 더 나뉨
def test_extract_events_detail():
    ratios = [0.5] * 8 + [0.84, 0.85, 0.84, 0.86] + [0.95] + [0.5] * 4
    ev = real_events.extract_events(ratios)[0]
    assert ev["shape"] == "OTHER"
    assert ev["detail"] == "NEAR_HOLD"
    