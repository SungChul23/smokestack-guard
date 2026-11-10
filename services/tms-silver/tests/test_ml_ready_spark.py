"""ml_ready_spark 테스트. 정답지는 같은 가짜 Silver에 C의 pandas `to_ml_ready`를 돌린 결과다."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql import types as T
from smokestack_guard.silver import ml_ready

import ml_ready_spark as mrs

KEYS = ["stack_code", "item_code", "measured_at"]
DOUBLE_COLS = [c for c in ml_ready.COLUMNS[3:29]]  # ratio_pct ~ label_ratio_60m
BOOL_COLS = ["feature_valid", "classification_eligible", "regression_eligible"]


@pytest.fixture(scope="module")
def ours(spark, ml_ready_silver_df):
    return mrs.to_ml_ready(ml_ready_silver_df).persist()


@pytest.fixture(scope="module")
def theirs(spark, ml_ready_silver_pdf, tmp_path_factory):
    """pandas 결과를 C처럼 to_parquet으로 쓰고(타임스탬프 ns 그대로) 같은 읽기 함수로 읽는다."""
    path = tmp_path_factory.mktemp("pandas") / "part.parquet"
    ml_ready.to_ml_ready(ml_ready_silver_pdf).to_parquet(path, index=False)
    df, _ = mrs.read_reference(spark, str(path))
    return df.persist()


def _row(df, stack, item, ts):
    rows = df.where((F.col("stack_code") == stack) & (F.col("item_code") == item)).where(
        F.col("measured_at") == F.lit(ts)
    ).collect()
    assert len(rows) == 1, (stack, item, ts)
    return rows[0]


# ---------------------------------------------------------------------------
# 1. pandas와 일치 (SC-003)
# ---------------------------------------------------------------------------


def test_matches_pandas_on_all_35_columns(ours, theirs):
    result = mrs.compare(ours, theirs)
    assert result["only_ours"] == 0 and result["only_theirs"] == 0, result
    assert result["column_mismatches"] == {c: 0 for c in ml_ready.COLUMNS if c not in KEYS}, result
    assert result["passed"] is True
    assert ours.count() == theirs.count() > 0


# ---------------------------------------------------------------------------
# 2. 컬럼 계약
# ---------------------------------------------------------------------------


def test_column_names_order_and_types(ours):
    assert ours.columns == ml_ready.COLUMNS
    types = dict(ours.dtypes)
    assert types["stack_code"] == types["item_code"] == "string"
    assert types["measured_at"] == "timestamp"
    assert all(types[c] == "double" for c in DOUBLE_COLS), types
    assert all(types[c] == "boolean" for c in BOOL_COLS), types
    assert all(types[c] == "string" for c in ml_ready.COLUMNS[-3:])


# ---------------------------------------------------------------------------
# 3~5. 공백·월 경계·라벨 사례를 직접 확인
# ---------------------------------------------------------------------------


def test_multi_day_gap_does_not_bridge(ours):
    after = _row(ours, "F001-P01", "nox", datetime(2023, 12, 1, 6, 30))
    assert after.ratio_lag_30m is None
    assert after.ratio_diff_30m is None
    assert after.feature_valid is False

    assert _row(ours, "F001-P01", "nox", datetime(2023, 12, 1, 8, 30)).feature_valid is False
    assert _row(ours, "F001-P01", "nox", datetime(2023, 12, 1, 9, 0)).feature_valid is True

    for ts in (datetime(2023, 11, 27, 16, 0), datetime(2023, 11, 27, 16, 30)):
        assert _row(ours, "F001-P01", "nox", ts).label_ratio_60m is None


def test_single_slot_gap(ours):
    # 11:00이 없다: 11:30의 30분 전 값은 null, 60분 전 값은 10:30
    r = _row(ours, "F002-P01", "nox", datetime(2025, 3, 10, 11, 30))
    assert r.ratio_lag_30m is None
    assert r.ratio_lag_60m == pytest.approx(57.3)
    assert r.ratio_rolling_mean_1h is None


def test_month_boundary_lag(ours):
    r = _row(ours, "F003-P01", "nox", datetime(2025, 10, 1, 0, 0))
    prev = _row(ours, "F003-P01", "nox", datetime(2025, 9, 30, 23, 30))
    assert r.ratio_lag_30m == prev.ratio_pct


@pytest.mark.parametrize(
    ("stack", "item", "ts", "expected"),
    [
        ("F004-P01", "nox", datetime(2025, 5, 1, 2, 30), 1.0),  # 85 → 88.3 → 92.7
        ("F004-P01", "nox", datetime(2025, 5, 1, 4, 0), 0.0),  # 80 → 82 → 84
        ("F004-P01", "nox", datetime(2025, 5, 1, 6, 0), None),  # 현재 95.2
        ("F005-P01", "sox", datetime(2025, 7, 1, 2, 30), None),  # 80 → 70 → (없음)
        ("F005-P01", "sox", datetime(2025, 7, 1, 5, 30), 1.0),  # 80 → 91 → (없음)
    ],
)
def test_label_entry_cases(ours, stack, item, ts, expected):
    assert _row(ours, stack, item, ts).label_entry_60m == expected


# ---------------------------------------------------------------------------
# 5-1. 적격 규칙 v2 (#33·#34)
# ---------------------------------------------------------------------------


def test_regression_includes_rows_at_or_above_90(ours):
    r = _row(ours, "F004-P01", "nox", datetime(2025, 5, 1, 6, 0))  # 현재 95.2
    assert r.feature_valid and r.label_ratio_60m is not None
    assert r.regression_eligible is True
    assert r.classification_eligible is False  # 분류는 그대로(현재 90% 이상이면 정답 없음)


@pytest.mark.parametrize(
    ("slot", "regression", "classification"),
    [
        (5, True, True),  # 창 0~7: 기준치 100만
        (7, False, False),  # 창 2~9: 100과 120(슬롯 8 공백 사이) → 빠짐. +60(슬롯 9)은 있다
        (14, True, True),  # 창 9~16: 120만 → 다시 학습 대상
    ],
)
def test_limit_change_across_gap_excludes_window(ours, slot, regression, classification):
    r = _row(ours, "F006-P01", "nox", datetime(2025, 8, 1) + slot * timedelta(minutes=30))
    assert r.feature_valid is True
    assert r.regression_eligible is regression
    assert r.classification_eligible is classification


def test_quality_policy_version_is_v2(ours):
    versions = ours.select("quality_policy_version").distinct().collect()
    assert {r.quality_policy_version for r in versions} == {"v2"}


def test_first_five_slots_are_not_feature_valid(ours):
    first = ours.groupBy("stack_code", "item_code").agg(F.min("measured_at").alias("t0"))
    joined = ours.join(first, ["stack_code", "item_code"]).where(
        F.col("measured_at") < F.col("t0") + F.expr("INTERVAL 150 MINUTES")
    )
    assert joined.count() > 0
    assert joined.where("feature_valid").count() == 0


# ---------------------------------------------------------------------------
# 6. 민감도: 행 기준 lag()는 pandas와 다르다
# ---------------------------------------------------------------------------


def test_row_based_lag_would_differ(ours, ml_ready_silver_df):
    norm = mrs.normalize(ml_ready_silver_df)
    w = Window.partitionBy("stack_code", "item_code").orderBy("measured_at")
    wrong = norm.withColumn("wrong_lag", F.lag("ratio_pct", 1).over(w)).select(*KEYS, "wrong_lag")
    diff = ours.join(wrong, KEYS).where(
        ~F.col("ratio_lag_30m").eqNullSafe(F.col("wrong_lag"))
    )
    assert diff.count() >= 1  # fixture가 공백을 실제로 담고 있다


# ---------------------------------------------------------------------------
# 7. 고르기
# ---------------------------------------------------------------------------


def test_selection_drops_non_target_rows(ours):
    assert ours.where(F.col("item_code") == "co").count() == 0
    assert _row(ours, "F001-P01", "nox", datetime(2023, 12, 1, 6, 30)).ratio_pct == pytest.approx(
        60.5
    )  # unit=% 행(10.0)이 아니라 ppm 행
    assert (
        ours.where(F.col("measured_at") == F.lit(datetime(2023, 12, 1, 10, 30))).count() == 0
    )  # other_code


# ---------------------------------------------------------------------------
# 8. K-TMS 정규화 형태 (#30 규칙)
# ---------------------------------------------------------------------------


def test_normalize_ktms_shape(spark):
    schema = T.StructType(
        [T.StructField(c, T.StringType()) for c in ("area_nm", "fact_manage_nm", "stack_code")]
        + [
            T.StructField("item", T.StringType()),
            T.StructField("value", T.DoubleType()),
            T.StructField("limit", T.DoubleType()),
            T.StructField("status", T.StringType()),
            T.StructField("ts_kst", T.TimestampType()),
            T.StructField("ratio", T.DoubleType()),
        ]
    )
    ts = datetime(2026, 11, 8, 10, 0)
    df = spark.createDataFrame(
        [
            ("가짜도", "가짜사업장", "1", "nox", 20.0, 50.0, "ok", ts, 0.4),
            ("가짜도", "가짜사업장", "1", "nox", 21.0, 50.0, "checking", ts, 0.42),
            ("가짜도", "가짜사업장", "1", "dust", 5.0, 10.0, "ok", ts, 0.5),
        ],
        schema,
    )
    rows = mrs.normalize(df).collect()
    assert len(rows) == 1
    assert rows[0].stack_code == "가짜도|가짜사업장|1"
    assert rows[0].measured_at == ts
    assert rows[0].ratio_pct == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# 9. 중복 키
# ---------------------------------------------------------------------------


def test_dedupe_keeps_smallest_ratio(spark):
    ts = datetime(2025, 1, 1, 0, 0)
    df = spark.createDataFrame(
        [("S", "nox", ts, 50.0, 50.0, 100.0), ("S", "nox", ts, 40.0, 40.0, 100.0)],
        "stack_code string, item_code string, measured_at timestamp, ratio_pct double, "
        "measure_value double, standard_value double",
    )
    out, dupes = mrs.dedupe(df)
    assert dupes == 1
    assert [r.ratio_pct for r in out.collect()] == [40.0]


# ---------------------------------------------------------------------------
# compare 자체 (T006)
# ---------------------------------------------------------------------------


def test_compare_detects_changes(ours):
    assert mrs.compare(ours, ours)["passed"] is True

    one_key = ours.where(F.col("measured_at") == F.lit(datetime(2025, 5, 1, 4, 0))).select(*KEYS)
    bumped = ours.join(one_key.withColumn("_hit", F.lit(True)), KEYS, "left").withColumn(
        "ratio_pct", F.when(F.col("_hit"), F.col("ratio_pct") + 1e-6).otherwise(F.col("ratio_pct"))
    ).select(*ml_ready.COLUMNS)
    result = mrs.compare(ours, bumped)
    assert result["column_mismatches"]["ratio_pct"] == 1
    assert len(result["mismatch_samples"]["ratio_pct"]) == 1
    assert result["passed"] is False

    tiny = ours.withColumn("ratio_pct", F.col("ratio_pct") + 2e-10)
    assert mrs.compare(ours, tiny)["passed"] is True

    missing = ours.join(one_key, KEYS, "left_anti")
    result = mrs.compare(missing, ours)
    assert result["only_theirs"] == 1 and result["only_ours"] == 0


# ---------------------------------------------------------------------------
# 이동 표준편차 허용 오차 (실데이터 21,739행, research.md R5)
# ---------------------------------------------------------------------------


def test_std_column_tolerance_and_max_diff(ours):
    assert mrs.COLUMN_ABS_TOL == {"ratio_rolling_std_3h": 1e-5}
    std = F.col("ratio_rolling_std_3h")

    small = ours.withColumn("ratio_rolling_std_3h", std + 5e-6)  # pandas 잔여 수준
    result = mrs.compare(ours, small)
    assert result["passed"] is True
    assert result["max_abs_diff"]["ratio_rolling_std_3h"] == pytest.approx(5e-6, rel=1e-3)
    assert result["tolerance"]["column_abs"] == {"ratio_rolling_std_3h": 1e-5}

    large = ours.withColumn("ratio_rolling_std_3h", std + 2e-5)
    assert mrs.compare(ours, large)["column_mismatches"]["ratio_rolling_std_3h"] > 0

    # 다른 컬럼은 기본(1e-9) 그대로
    other = ours.withColumn("ratio_rolling_mean_3h", F.col("ratio_rolling_mean_3h") + 5e-6)
    assert mrs.compare(ours, other)["passed"] is False


def test_nan_to_null(spark):
    df = spark.createDataFrame([(float("nan"), "a"), (1.5, "b")], "x double, s string")
    out = mrs.nan_to_null(df).orderBy("s").collect()
    assert out[0].x is None and out[1].x == 1.5
