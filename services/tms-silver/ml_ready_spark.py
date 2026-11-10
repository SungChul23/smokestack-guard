"""Silver → ML-ready (Spark).

C의 pandas `smokestack_guard.silver.ml_ready.to_ml_ready`와 같은 결과를 낸다.

규칙의 기준은 C의 `ml_ready.py`다. 의미를 바꾸지 말 것.
바뀌면 `tests/test_ml_ready_spark.py`가 잡는다.

pandas는 굴뚝·항목마다 30분 격자의 빈 칸을 채운 뒤 shift/rolling 한다. 여기서는 격자를 만들지 않고
`slot = unix_timestamp / 1800`(정수) 위의 범위 윈도우(rangeBetween)로 같은 의미를 얻는다.
- "k칸 전 값" = 정확히 slot-k 슬롯의 값, 없으면 null (행 기준 lag()를 쓰지 않는다)
- "최근 n칸 통계" = 그 범위에 관측이 n개 모두 있을 때만 계산

설계: specs/a-platform/005-tw-cems-ml-ready-spark/research.md R1~R3
"""

from __future__ import annotations

import math
from functools import reduce

from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T
from smokestack_guard.silver.ml_ready import (
    COLUMNS,
    ENTRY_PCT,
    FEATURE_VERSION,
    LABEL_VERSION,
    LAGS,
    ML_ITEMS,
    QUALITY_POLICY_VERSION,
    WINDOW,
)

KEYS = ["stack_code", "item_code", "measured_at"]
# 컬럼별 절대 허용 오차(기본보다 넓게). research.md R5
# 이동 표준편차: 6칸 값이 모두 같은 창(표준편차 정확히 0)에서 pandas의 누적 rolling std가 직전에
# 빠져나간 값의 계산 잔여로 0 대신 아주 작은 값을 낸다.
# (2026-11-09 실데이터 21,739행, C도 1.6e-6 기록)
# 단위가 %p라 1e-5는 학습에 영향이 없다. 실제 최대 차이는 compare 기록의 max_abs_diff로 남긴다.
COLUMN_ABS_TOL = {"ratio_rolling_std_3h": 1e-5}
SLOT_SECONDS = 30 * 60
BOOL_COLUMNS = ["feature_valid", "classification_eligible", "regression_eligible"]
STRING_COLUMNS = ["stack_code", "item_code", "feature_version", "label_version",
                  "quality_policy_version"]  # fmt: skip


# ---------------------------------------------------------------------------
# 입력 정규화 (#30 규칙: tw_cems와 ktms 모두)
# ---------------------------------------------------------------------------


def normalize(silver: DataFrame) -> DataFrame:
    """Silver → (stack_code, item_code, measured_at, ratio_pct, measure_value, standard_value)."""
    cols = set(silver.columns)
    df = silver.where((F.col("status") == "ok") & F.col("item").isin(*ML_ITEMS))
    if "unit" in cols:  # ktms has no unit column; its nox/sox are taken as ppm
        df = df.where(F.col("unit") == "ppm")
    if "ts_local" in cols:  # tw_cems: Taiwan wall clock
        clock, stack = F.col("ts_local"), F.col("stack_code")
    else:  # ktms: no single stack id, so area + facility + stack_code
        clock = F.col("ts_kst")
        stack = F.concat_ws("|", "area_nm", "fact_manage_nm", "stack_code")
    return df.select(
        stack.alias("stack_code"),
        F.col("item").alias("item_code"),
        clock.alias("measured_at"),
        (F.col("ratio").cast("double") * 100).alias("ratio_pct"),
        F.col("value").cast("double").alias("measure_value"),
        F.col("limit").cast("double").alias("standard_value"),
    )


def dedupe(df: DataFrame) -> tuple[DataFrame, int]:
    """같은 키가 여러 행이면 ratio_pct가 가장 작은 행을 남긴다(결정적). 중복 건수도 돌려준다."""
    w = Window.partitionBy(*KEYS).orderBy(F.col("ratio_pct").asc_nulls_last())
    ranked = df.withColumn("_rn", F.row_number().over(w))
    dupes = ranked.where(F.col("_rn") > 1).count()
    return ranked.where(F.col("_rn") == 1).drop("_rn"), dupes


# ---------------------------------------------------------------------------
# 피처·라벨
# ---------------------------------------------------------------------------


def add_features(df: DataFrame) -> DataFrame:
    df = df.withColumn(
        "_slot", F.floor(F.unix_timestamp("measured_at") / SLOT_SECONDS).cast("long")
    )
    w = Window.partitionBy("stack_code", "item_code").orderBy("_slot")
    r = F.col("ratio_pct")

    def at(k: int) -> Column:  # exactly k slots away (negative = past), null if absent
        return F.first("ratio_pct").over(w.rangeBetween(k, k))

    def last_n(n: int) -> Window:
        return w.rangeBetween(-(n - 1), 0)

    steps = [m // 30 for m in LAGS]  # 1..5
    past = {k: at(-k) for k in range(1, WINDOW)}  # 1..WINDOW-1
    nxt1, nxt2 = at(1), at(2)

    full1h, full3h = last_n(2), last_n(WINDOW)
    has1h = F.count("ratio_pct").over(full1h) == 2
    has3h = F.count("ratio_pct").over(full3h) == WINDOW

    def when3h(expr: Column) -> Column:
        return F.when(has3h, expr)

    # least-squares slope over the last WINDOW points, same weights and order as pandas
    center = (WINDOW - 1) / 2
    denom = sum((k - center) ** 2 for k in range(WINDOW))
    series = [r] + [past[j] for j in range(1, WINDOW)]  # j = 0..WINDOW-1
    slope = reduce(
        lambda acc, term: acc + term,
        [F.lit(WINDOW - 1 - j - center) * series[j] for j in range(WINDOW)],
        F.lit(0.0),
    ) / F.lit(denom)

    diffs = [series[j] - series[j + 1] for j in range(WINDOW - 1)]
    rise = F.when(
        reduce(lambda a, b: a & b, [d.isNotNull() for d in diffs]),
        reduce(lambda a, b: a + b, [F.when(d > 0, 1.0).otherwise(0.0) for d in diffs]),
    )

    d30 = r - past[1]
    two_pi = F.lit(2 * math.pi)
    hour = F.hour("measured_at").cast("double")
    month = F.month("measured_at").cast("double")

    below = r < F.lit(ENTRY_PCT)
    reached = F.coalesce(nxt1 >= F.lit(ENTRY_PCT), F.lit(False)) | F.coalesce(
        nxt2 >= F.lit(ENTRY_PCT), F.lit(False)
    )
    known = reached | (nxt1.isNotNull() & nxt2.isNotNull())
    label_entry = F.when(below & known, F.when(reached, 1.0).otherwise(0.0))

    # v2: 행의 창(과거 150분 ~ 미래 60분 = slot-5 ~ slot+2)에 서로 다른 기준치가 있으면
    # 학습 대상에서 뺀다. 빈 슬롯을 사이에 둬도 해당한다.
    # pandas의 rolling(WINDOW + 2).max - min, shift(-2)와 같은 범위다.
    limit_window = w.rangeBetween(-(WINDOW - 1), 2)
    limit_changed = F.coalesce(
        F.max("standard_value").over(limit_window) - F.min("standard_value").over(limit_window)
        > F.lit(0.0),
        F.lit(False),
    )

    out = df.select(
        "stack_code",
        "item_code",
        "measured_at",
        r.alias("ratio_pct"),
        (F.lit(ENTRY_PCT) - r).alias("headroom_pct"),
        "measure_value",
        "standard_value",
        *[past[k].alias(f"ratio_lag_{k * 30}m") for k in steps],
        d30.alias("ratio_diff_30m"),
        (r - past[2]).alias("ratio_diff_60m"),
        F.when(has1h, F.avg("ratio_pct").over(full1h)).alias("ratio_rolling_mean_1h"),
        when3h(F.avg("ratio_pct").over(full3h)).alias("ratio_rolling_mean_3h"),
        when3h(F.stddev_samp("ratio_pct").over(full3h)).alias("ratio_rolling_std_3h"),
        when3h(F.max("ratio_pct").over(full3h)).alias("ratio_rolling_max_3h"),
        when3h(F.max("ratio_pct").over(full3h) - F.min("ratio_pct").over(full3h)).alias(
            "ratio_range_3h"
        ),
        slope.alias("ratio_slope_3h"),
        rise.alias("rise_count_3h"),
        (d30 - (past[1] - past[2])).alias("ratio_acceleration"),
        F.sin(two_pi * hour / 24.0).alias("hour_sin"),
        F.cos(two_pi * hour / 24.0).alias("hour_cos"),
        F.sin(two_pi * month / 12.0).alias("month_sin"),
        F.cos(two_pi * month / 12.0).alias("month_cos"),
        F.weekday("measured_at").cast("double").alias("day_of_week"),  # Monday = 0, like pandas
        label_entry.alias("label_entry_60m"),
        nxt2.alias("label_ratio_60m"),
        has3h.alias("feature_valid"),
        limit_changed.alias("_limit_changed"),
    )
    out = (
        out.withColumn(
            "classification_eligible",
            F.col("feature_valid")
            & F.col("label_entry_60m").isNotNull()
            & ~F.col("_limit_changed"),
        )
        .withColumn(  # v2: 현재 90% 이상인 행도 회귀 대상이다
            "regression_eligible",
            F.col("feature_valid")
            & F.col("label_ratio_60m").isNotNull()
            & ~F.col("_limit_changed"),
        )
        .withColumn("feature_version", F.lit(FEATURE_VERSION))
        .withColumn("label_version", F.lit(LABEL_VERSION))
        .withColumn("quality_policy_version", F.lit(QUALITY_POLICY_VERSION))
    )
    return cast_contract(out.select(*COLUMNS))


def cast_contract(df: DataFrame) -> DataFrame:
    """컬럼을 data-model.md §2 타입으로 맞춘다."""

    def target(c: str) -> str:
        if c == "measured_at":
            return "timestamp"
        if c in BOOL_COLUMNS:
            return "boolean"
        if c in STRING_COLUMNS:
            return "string"
        return "double"

    return df.select(*[F.col(c).cast(target(c)).alias(c) for c in COLUMNS])


def to_ml_ready(silver: DataFrame) -> DataFrame:
    deduped, _ = dedupe(normalize(silver))
    return add_features(deduped)


def ml_ready_stats(df: DataFrame) -> dict:
    """실행 기록용 건수 (data-model.md §4)."""

    def counts(frame: DataFrame) -> dict:
        row = frame.agg(
            F.count(F.lit(1)).alias("output_rows"),
            F.sum(F.col("feature_valid").cast("long")).alias("feature_valid_rows"),
            F.sum(F.col("classification_eligible").cast("long")).alias(
                "classification_eligible_rows"
            ),
            F.sum(F.col("regression_eligible").cast("long")).alias("regression_eligible_rows"),
            F.sum((F.col("label_entry_60m") == 1.0).cast("long")).alias("positive_rows"),
            F.sum(
                (F.col("classification_eligible") & (F.col("label_entry_60m") == 1.0)).cast("long")
            ).alias("eligible_positive_rows"),
        ).collect()[0]
        return {k: int(v or 0) for k, v in row.asDict().items()}

    stats = counts(df)
    items = [r.item_code for r in df.select("item_code").distinct().collect()]
    stats["by_item"] = {
        item: counts(df.where(F.col("item_code") == item)) for item in sorted(items)
    }
    return stats


# ---------------------------------------------------------------------------
# 정답지 읽기와 비교 (research.md R5·R6)
# ---------------------------------------------------------------------------


def nan_to_null(df: DataFrame) -> DataFrame:
    """pandas의 NaN을 Spark null로 맞춘다. 비교에서 NaN과 null을 같은 '값 없음'으로 본다."""
    doubles = {c for c, t in df.dtypes if t == "double"}
    return df.select(
        *[F.when(~F.isnan(c), F.col(c)).alias(c) if c in doubles else F.col(c) for c in df.columns]
    )


def read_reference(spark: SparkSession, path: str) -> tuple[DataFrame, str]:
    """pandas가 쓴 ML-ready Parquet을 읽는다.

    ns 타임스탬프는 Spark 3.5가 그대로 못 읽어 정수로 읽은 뒤 timestamp로 바꾼다.
    """
    spark.conf.set("spark.sql.legacy.parquet.nanosAsLong", "true")
    df = spark.read.parquet(path)
    original = dict(df.dtypes)["measured_at"]
    if isinstance(df.schema["measured_at"].dataType, T.LongType):  # ns since epoch
        df = df.withColumn("measured_at", F.timestamp_micros(F.floor(F.col("measured_at") / 1000)))
    return nan_to_null(cast_contract(df.select(*COLUMNS))), original


def compare(
    ours: DataFrame,
    theirs: DataFrame,
    abs_tol: float = 1e-9,
    rel_tol: float = 1e-9,
    samples: int = 5,
) -> dict:
    """키로 full outer join 해서 한쪽에만 있는 키와 컬럼별 불일치를 센다. 값은 돌려주지 않는다."""
    value_cols = [c for c in COLUMNS if c not in KEYS]
    o = ours.select(*KEYS, *[F.col(c).alias(f"o__{c}") for c in value_cols]).withColumn(
        "_o", F.lit(True)
    )
    t = cast_contract(theirs).select(
        *KEYS, *[F.col(c).alias(f"t__{c}") for c in value_cols]
    ).withColumn("_t", F.lit(True))
    joined = o.join(t, KEYS, "full").persist()

    both = F.col("_o").isNotNull() & F.col("_t").isNotNull()
    numeric = {c for c, typ in ours.dtypes if typ == "double"}

    def same(c: str) -> Column:
        a, b = F.col(f"o__{c}"), F.col(f"t__{c}")
        if c in numeric:
            tol = max(abs_tol, COLUMN_ABS_TOL.get(c, 0.0))
            close = F.abs(a - b) <= F.lit(tol) + F.lit(rel_tol) * F.abs(b)
            return (a.isNull() & b.isNull()) | (a.isNotNull() & b.isNotNull() & close)
        return a.eqNullSafe(b)

    aggs = [
        F.count(F.lit(1)).alias("_rows"),
        F.sum(F.col("_o").isNotNull().cast("long")).alias("ours_rows"),
        F.sum(F.col("_t").isNotNull().cast("long")).alias("theirs_rows"),
        F.sum((F.col("_o").isNotNull() & F.col("_t").isNull()).cast("long")).alias("only_ours"),
        F.sum((F.col("_o").isNull() & F.col("_t").isNotNull()).cast("long")).alias("only_theirs"),
    ] + [F.sum((both & ~same(c)).cast("long")).alias(f"m__{c}") for c in value_cols] + [
        F.max(F.abs(F.col(f"o__{c}") - F.col(f"t__{c}"))).alias(f"d__{c}")
        for c in value_cols
        if c in numeric
    ]
    row = joined.agg(*aggs).collect()[0].asDict()

    mismatches = {c: int(row[f"m__{c}"] or 0) for c in value_cols}
    sample_keys = {}
    for c, n in mismatches.items():
        if n:
            picked = joined.where(both & ~same(c)).select(*KEYS).orderBy(*KEYS).limit(samples)
            sample_keys[c] = [
                [r.stack_code, r.item_code, r.measured_at.isoformat()] for r in picked.collect()
            ]
    joined.unpersist()

    result = {
        "ours_rows": int(row["ours_rows"] or 0),
        "theirs_rows": int(row["theirs_rows"] or 0),
        "only_ours": int(row["only_ours"] or 0),
        "only_theirs": int(row["only_theirs"] or 0),
        "column_mismatches": mismatches,
        "mismatch_samples": sample_keys,
        # 두 값이 모두 있는 행에서 |ours - theirs|의 최댓값 (값 자체가 아니라 차이의 크기)
        "max_abs_diff": {
            c: float(row[f"d__{c}"]) for c in value_cols if c in numeric and row[f"d__{c}"]
        },
        "tolerance": {"abs": abs_tol, "rel": rel_tol, "column_abs": dict(COLUMN_ABS_TOL)},
    }
    result["passed"] = (
        result["only_ours"] == 0 and result["only_theirs"] == 0 and not any(mismatches.values())
    )
    return result
