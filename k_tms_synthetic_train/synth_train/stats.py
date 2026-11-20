'''
- 통계 읽기: 실측 통계 csv에서 '본보기 굴뚝' 후보를 거르고 하나를 뽑음
'''
import numpy as np
import pandas as pd

# 숫자로 바꿔 읽을 컬럼 (csv에서는 모두 글자로 읽혀 변환 필요)
NUMERIC_COLS = [
    "n_valid", "mean", "std", "phi", "p50", "p99", "max_pct", "perm_std", "perm_distinct",
]

# 통계 csv 읽어오기 (비어있거나 이상한 값은 NaN)
def load_ref_stats(path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding = "utf-8-sig")      # CSV를 df형식으로 읽고 첫 컬럼 이름이 꺠지지 않게 설정(utf-8-sig)
    for col in NUMERIC_COLS:                                       # 숫자여야 하는 컬럼들을 하나씩 숫자로 바꿈
        df[col] = pd.to_numeric(df[col], errors = "coerce")        # errors = 'coerce': 바꿀 수 없는 값은 에러 대신 NaN으로 설정
    return df

# 시계열을 만들때 유효한 굴뚝만 남김
def usable(df: pd.DataFrame, min_valid: int = 200) -> pd.DataFrame:
    mask = (
        (df["n_valid"] >= min_valid) &          # 측정이 충분해야 평균, 변동 패턴을 믿을 수 있음
        (df["std"] > 0) &                       # 값이 전혀 안 변하는 굴뚝은 변동 패턴을 만들 수 없음
        df["phi"].notna() &                     # 자기상관이 계산되어 있어야 함
        (df["perm_distinct"] == 1)              # 허용기준이 한 가지여야 에피소드 안에서 값을 고정할 수 있음
    )
    return df[mask].reset_index(drop = True)

# 평범한 시나리오 (S-01, S-06, S-08)용 후보를 고름
def filter_normal(df: pd.DataFrame, cond: dict) -> pd.DataFrame:
    mean_lo, mean_hi = cond["mean"]   
    phi_lo, phi_hi = cond["phi"]
    mask = (
        df["mean"].between(mean_lo, mean_hi) &  # 평균 기준대비율이 이 범위
        df["phi"].between(phi_lo, phi_hi) &     # 자기상관이 이 범위
        (df["p99"] < cond["p99_max"])           # 상위 99%값이 이값 미만(평소 80%를 안 넘는 곳)
    )
    return df[mask].reset_index(drop = True)

# 정해진 모양의 시나리오(S-02~S-05)용 후보를 고름
def filter_trajectory(df: pd.DataFrame, first_value: float, cond: dict) -> pd.DataFrame:
    gap = (first_value - df["mean"]).abs()              # 정해진 모양의 첫 값과 각 굴뚝의 평균이 얼마나 떨어져 있는지 계산
    mask = (                                               # 두 조건을 모두 만족하는 굴뚝만 True로 표시
        (df["p99"] < cond["p99_max"]) &                         # 조건 1: 평소 상위 99% 값이 80% 미만의 굴뚝
        (gap <= cond["first_value_within_sigma"] * df["std"])   # 조건 2: 첫 값과 평균의 거리가 "표준편차 * 2.0" 이내인 굴뚝
    )
    return df[mask].reset_index(drop = True)

# 후보 중 한 줄을 무작위로 뽑음
def pick_one(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    if df.empty:                                                                # 후보가 하나도 없다면 에러로 알림
        raise ValueError("조건에 맞는 참조 굴뚝이 존재하지 않음. 조건 재확인")    
    return df.iloc[int(rng.integers(len(df)))]                                  # 0 이상 n 미만의 정수, int(...)로 일반 정수로 바꿔 iloc에 넣음


# NOX + SOX 변형용: 한 굴뚝에서 NOX와 SOX 둘 다 재는 참조 굴뚝을 하나 골라 그 굴뚝의 오르는 항목 통계와 정상인 다른 항목 통계를 한 쌍으로 돌려줌                                                                                                                                                             # NOX+SOX 에피소드용: 같은 굴뚝의 NOX, SOX 한 쌍을 고름
def pick_pair(df: pd.DataFrame, rising_item: str, first_value: float, traj_cond: dict, normal_cond: dict, min_valid: int, rng: np.random.Generator) -> dict:
    # 쓸 수 있는 줄만 남기고(usable), 그 중 NOX, SOX 둘 다 재는 굴뚝만 고름
    both = usable(df[df["items_measured"] == "NOX+SOX"], min_valid)
    # 오르지 않는 쪽 항목 이름을 정함 (오르는게 NOX면 SOX, 아니면 NOX)
    other_item = "SOX" if rising_item == "NOX" else "NOX"
    # 오르는 항목 후보: 첫 값 근처에서 시작하고 p99가 80미만인 굴뚝 (궤적 조건)
    rising_rows = filter_trajectory(both[both["item"] == rising_item], first_value, traj_cond)
    # 다른 굴뚝 후보: 평소 평균 / 자기상관 범위에 드는 정상 굴뚝
    other_rows = filter_normal(both[both["item"] == other_item], normal_cond)
    # 굴뚝을 구별하는 키. 이름과 코드를 함께 써야 같은 굴뚝인지 확실해짐
    key = ["fact_manage_nm", "stack_code"]
    # 두 후보 목록의 키를 맞춰 합침. 양쪽 조건을 모두 만족하는 굴뚝만 남음 
    pairs = rising_rows[key].merge(other_rows[key], on = key)
    # 남은 굴뚝 중 하나를 무작위로 고름. 없으면 pick_one이 에러를 냄
    chosen = pick_one(pairs, rng)
    # 고른 굴뚝의 줄을 후보표에서 찾아 주는 함수
    def row_of(rows):
        # 이름과 코드가 둘 다 고른 굴뚝과 같은 줄을 표시
        mask = (rows["fact_manage_nm"] == chosen["fact_manage_nm"]) & (rows["stack_code"] == chosen["stack_code"])
        # 표시된 줄 중 첫 번째를 돌려줌
        return rows[mask].iloc[0]
    # 오르는 항목의 통계 줄과 다른 항목의 통계 줄을 한 쌍으로 돌려줌
    return {"rising": row_of(rising_rows), "other": row_of(other_rows)}