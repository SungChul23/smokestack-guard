"""시나리오 B의 입력 출처·고정 계약. 분할·혼합·학습은 실행하지 않는다."""
from dataclasses import dataclass

REGION = "ap-northeast-2"
ATHENA_DATABASE = "tms_silver2"
ATHENA_WORKGROUP = "tms-eda"
CEMS_INPUT_URI = "s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/"
BATCH_SIZE = 65536

# 후속 분할 단계에서 사용할 승인된 상한. 현재 로더는 분할하지 않는다.
DOMESTIC_CONFIRMED_END_EXCLUSIVE = "2026-11-17 00:00:00"
DOMESTIC_TEST_END_EXCLUSIVE = "2026-11-16 23:00:00"

FEATURE_COLUMNS = (
    "ratio_pct", "headroom_pct",
    "ratio_lag_30m", "ratio_lag_60m", "ratio_lag_90m",
    "ratio_lag_120m", "ratio_lag_150m",
    "ratio_diff_30m", "ratio_diff_60m", "ratio_acceleration",
    "ratio_rolling_mean_1h", "ratio_rolling_mean_3h",
    "ratio_rolling_std_3h", "ratio_rolling_max_3h", "ratio_range_3h",
    "ratio_slope_3h", "rise_count_3h",
    "hour_sin", "hour_cos", "month_sin", "month_cos", "day_of_week",
)
NUMERIC_COLUMNS = (*FEATURE_COLUMNS, "measure_value", "standard_value",
                   "label_entry_60m", "label_ratio_60m")
FLAG_COLUMNS = ("feature_valid", "classification_eligible", "regression_eligible")
VERSION_VALUES = {"feature_version": "v1", "label_version": "v1",
                  "quality_policy_version": "v2"}
STRING_COLUMNS = ("stack_code", "item_code", *VERSION_VALUES)
REQUIRED_COLUMNS = ("stack_code", "item_code", "measured_at",
                    *NUMERIC_COLUMNS, *FLAG_COLUMNS, *VERSION_VALUES)
LOAD_COLUMNS = (*REQUIRED_COLUMNS, "data_source")


@dataclass(frozen=True)
class Source:
    timezone: str
    table: str | None = None
    snapshot_id: int | None = None
    train_only: bool = False


SOURCES = {
    "tw_cems": Source("Asia/Taipei"),
    "ktms": Source("Asia/Seoul", "ktms_ml_ready", 5488575191367819703),
    "ktms_synth": Source("Asia/Seoul", "ktms_synth_ml_ready",
                         6619206033361917612, train_only=True),
}


def check_source(source: str, purpose: str = "inspection") -> Source:
    """purpose는 출처 사용 제한만 확인하며 날짜 분할을 뜻하지 않는다."""
    if source not in SOURCES:
        raise ValueError(f"알 수 없는 데이터 출처: {source}")
    if purpose not in ("inspection", "train", "validation", "test"):
        raise ValueError(f"알 수 없는 사용 목적: {purpose}")
    config = SOURCES[source]
    if config.train_only and purpose in ("validation", "test"):
        raise ValueError("국내 합성데이터는 Train 전용입니다")
    return config

# 승인된 B 분류 실험. 다른 하이퍼파라미터는 향후 학습 모듈에서 A W10/W5를 계승한다.
CLASSIFICATION_MODELS = {
    "N2-C": {"pollutant": "nox", "scale_pos_weight": 10},
    "S2-C": {"pollutant": "sox", "scale_pos_weight": 5},
}
SOURCE_WEIGHTS = {
    "A": {"tw_cems": 1.0, "ktms": 1.0, "ktms_synth": 1.0},
    "B": {"tw_cems": 1.0, "ktms": 5.0, "ktms_synth": 1.0},
    "C": {"tw_cems": 1.0, "ktms": 10.0, "ktms_synth": 1.0},
}
