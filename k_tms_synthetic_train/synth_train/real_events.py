'''
- real_events: 실측 시계열(CSV)에서 사건을 뽑고, 모양, 직전 단서를 붙임
'''
import pandas as pd
from synth_train import shapes

# CSV -> {(성분, 사업장, 굴뚝코드): [30분 칸마다 비율 또는 None]}
def load_series(path, start, end) -> dict:
    # 굴뚝 코드는 숫자가 아니라 문자로 읽음 
    df = pd.read_csv(path, dtype={"stack_code": str}, encoding = "utf-8-sig")
    df["mesure_dt"] = pd.to_datetime(df["mesure_dt"])

    # start-end를 30분 간격으로 나눈 격자, 이 격자가 모든 굴뚝의 공통 시간축
    grid = pd.date_range(start, end, freq = "30min")
    out = {}
    # 같은 코드라도 사업장이 다르면 다른 굴뚝이라 셋을 함께 묶음
    for key, g in df.groupby(["item", "fact_manage_nm", "stack_code"]):
        s = g.set_index("mesure_dt")["ratio"]                  
        s = s[~s.index.duplicated(keep = "last")]                   
        s = s.reindex(grid)
        out[key] = [None if pd.isna(v) else float(v) for v in s]
    return out

# 직전 단서: 사건 첫 행의 30분 전 또는 60분 전에 유효한 값이 있으면 True
def has_cue(ratios, event) -> bool:
    start = event["rows"][0]
    for k in (1, 2):
        i = start - k
        if i >= 0 and ratios[i] is not None:
            return True
    return False

# 한 굴뚝의 비율 목록 -> 사건 목록 [{"shape", "cue", "start", "curve"}]
def extract_events(ratios) -> list:
    out = []
    for ev in shapes.find_events(ratios):
        rows = ev["rows"]
        start = ev["rows"][0]
        after_i = rows[-1] + 1
        curve = [ratios[i] if 0 <= i < len(ratios) else None for i in range(start - 4, start + 3)]
        out.append({
            "shape": shapes.classify_event(ratios, ev),
            "cue": has_cue(ratios, ev),
            "start": start,
            "curve": curve,
            "high_rows": len(rows),
            "peak": max(ratios[i] for i in rows),
            "entries": ev["entries"],
            "after": ratios[after_i] if after_i < len(ratios) else None,
            "detail": shapes.classify_event_detail(ratios, ev)
        })
    return out
