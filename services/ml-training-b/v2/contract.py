"""부분 이력 전용 적격 마스크. 원본 플래그와 Feature 값은 변경하지 않는다."""
import numpy as np
import pandas as pd
from config import FEATURE_COLUMNS
from contract import validate_contract

# C Spark 생성 코드에서 확인한 정책. Silver status=ok, nox/sox, ppm만 정규화한다.
C_POLICY_REFERENCE = "services/tms-silver/ml_ready_spark.py@blob:583a1e62ea00d63a34d1bb14b4267231eee5da05"
BASE_FEATURES = ("ratio_pct", "headroom_pct", "ratio_lag_30m",
                 "ratio_diff_30m", "ratio_rolling_mean_1h",
                 "hour_sin", "hour_cos", "month_sin", "month_cos", "day_of_week")


def eligibility(data, index, *, normalized_silver_confirmed=False):
    """기존 적격 행은 유지하고, 증명 가능한 이력 부족 행만 추가한다.

    오프라인 학습·평가 전용이며 실시간 추론 적격 판정에 사용하지 않는다.
    index는 전체 동일 입력의 시계열 인덱스다. 배치 밖 과거/미래도 정확한 슬롯으로 찾는다.
    미래는 저장 Label 검증과 기준치 변경 제외에만 사용한다.
    Silver status/unit은 ML-ready에 없으므로 정규화 출처 확인 없이는 부분 행을 추가하지 않는다.
    """
    validate_contract(data, "tw_cems")  # 기존 적격 행 검증을 약화하지 않는다.
    x = data.loc[:, list(FEATURE_COLUMNS)].to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(x).any():
        raise ValueError("Feature에 Inf가 있습니다. NaN만 결측으로 허용합니다")
    baseline = (data.classification_eligible.eq(True)
                & data.feature_valid.eq(True)).fillna(False).to_numpy()
    k = index.keys_for(data)
    past = [index.lookup(k - j) for j in range(6)]
    # lookup: ratio, measure, standard, exists. 유효한 현재와 정확히 30분 전 관측이 필수다.
    def valid_observation(v):
        return v[3] & np.isfinite(v[0]) & np.isfinite(v[1]) & np.isfinite(v[2]) & (v[2] > 0)
    minimum = valid_observation(past[0]) & valid_observation(past[1])
    history = np.column_stack([v[0] for v in past])
    missing_history = ~np.isfinite(history).all(axis=1)
    base_finite = np.isfinite(data.loc[:, list(BASE_FEATURES)].to_numpy(
        dtype=float, na_value=np.nan)).all(axis=1)
    # NaN은 실제 누락된 과거 값 또는 그 값에 의존하는 통계에서만 허용한다.
    explained = np.ones(len(data), bool)
    for j in range(1, 6):
        explained &= (~data[f"ratio_lag_{30*j}m"].isna().to_numpy()
                      | ~np.isfinite(history[:, j]))
    for col in ("ratio_diff_60m", "ratio_acceleration"):
        explained &= ~data[col].isna().to_numpy() | ~np.isfinite(history[:, 2])
    for col in ("ratio_rolling_mean_3h", "ratio_rolling_std_3h",
                "ratio_rolling_max_3h", "ratio_range_3h", "ratio_slope_3h", "rise_count_3h"):
        explained &= ~data[col].isna().to_numpy() | missing_history
    # C v2: slot-5..slot+2의 관측된 기준치 max-min >0이면 제외. 빈 슬롯은 채우지 않는다.
    stable = np.ones(len(data), bool)
    standard = past[0][2]
    for j in range(-5, 3):
        observation = index.lookup(k + j)
        observed = observation[3]
        stable &= ~observed | (np.isfinite(observation[2])
                               & (observation[2] > 0) & (observation[2] == standard))
    f30, f60 = index.lookup(k + 1), index.lookup(k + 2)
    reached = ((valid_observation(f30) & (f30[0] >= 90))
               | (valid_observation(f60) & (f60[0] >= 90)))
    both = valid_observation(f30) & valid_observation(f60)
    y = data.label_entry_60m.to_numpy(dtype=float, na_value=np.nan)
    known_label = np.isin(y, (0, 1)) & (reached | both) & (y == reached.astype(float))
    partial = (bool(normalized_silver_confirmed)
               & data.feature_valid.eq(False).fillna(False).to_numpy()
               & ~data.classification_eligible.eq(True).fillna(False).to_numpy()
               & minimum & (past[0][0] < 90) & missing_history
               & base_finite & explained & stable & known_label)
    return pd.DataFrame({"baseline": baseline, "partial": partial,
                         "eligible_v2": baseline | partial}, index=data.index)
