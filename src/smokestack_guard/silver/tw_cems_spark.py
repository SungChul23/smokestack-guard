"""Spark version of tw_cems.py (same rules; constants are imported from it). Needs Spark >= 3.3."""
from __future__ import annotations

import argparse

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from smokestack_guard.silver.tw_cems import COLUMNS, ITEMS, RAW, STACK, USABLE_CODE2


def _number(col: str):
    """Like pandas to_numeric(errors="coerce"), but unparsable and NaN both become null."""
    x = F.col(col).cast("double")
    return F.when(~F.isnan(x), x)


def prep(df: DataFrame) -> DataFrame:
    df = df.toDF(*[c.lower() for c in df.columns])
    for c in RAW:
        if c not in df.columns:
            df = df.withColumn(c, F.lit(None).cast("string"))
    item_map = F.create_map(*[F.lit(x) for kv in ITEMS.items() for x in kv])
    limit = _number("std")
    return df.select(
        F.coalesce("epb_county", F.lit("")).alias("area_nm"),
        F.coalesce("abbr", F.lit("")).alias("fact_manage_nm"),
        F.concat(F.col("cno"), F.lit("-"), F.col("polno")).alias("stack_code"),
        F.coalesce(item_map[F.col("item")], F.col("item")).alias("item"),
        F.coalesce("unit", F.lit("")).alias("unit"),
        (F.col("m_time").cast("timestamp") + F.expr("INTERVAL 1 HOUR")).alias("ts"),  # Taipei -> KST
        _number("m_value").alias("value"),
        F.when(limit > 0, limit).alias("limit"),
        F.coalesce("code2", F.lit("")).alias("code2"),
    ).where(F.col("stack_code").isNotNull() & F.col("ts").isNotNull())


def to_silver(df: DataFrame) -> DataFrame:
    d = df if "ts" in df.columns else prep(df)
    key = STACK + ["item", "unit"]
    d = d.dropDuplicates(key + ["ts", "value", "limit", "code2"])

    d = d.withColumn("num", F.col("value").isNotNull() & (F.count(F.lit(1)).over(Window.partitionBy(*key, "ts")) == 1))
    num = F.col("num")
    num_value, num_limit = F.when(num, F.col("value")), F.when(num, F.col("limit"))
    pos = F.minute("ts") % 30
    p0, p15 = num & (pos == 0), num & (pos == 15)
    code_ok = num & F.col("code2").rlike(f"^(?:{USABLE_CODE2})$")
    first_limit = F.min(F.when(F.col("limit").isNotNull(), F.struct("ts", "limit")))
    slot = F.timestamp_seconds(F.floor(F.unix_timestamp("ts") / 1800) * 1800)

    out = d.groupBy(*key, slot.alias("slot")).agg(
        F.avg(num_value).alias("value"),
        first_limit.getField("limit").alias("limit"),
        F.countDistinct(num_limit).alias("n_limits"),
        F.max(p0.cast("int")).alias("has_p0"),
        F.max(p15.cast("int")).alias("has_p15"),
        F.sum(num.cast("int")).alias("n_num"),
        F.sum(code_ok.cast("int")).alias("n_code_ok"),
        F.min(F.struct("ts", "code2")).getField("code2").alias("code2_a"),
        F.max(F.struct("ts", "code2")).getField("code2").alias("code2_b"),
    )

    pair = (F.col("has_p0") == 1) & (F.col("has_p15") == 1) & (F.col("n_limits") <= 1)
    both_ok = pair & (F.col("n_code_ok") == 2)
    ratio = F.when(pair, F.col("value")) / F.col("limit")
    a, b = F.col("code2_a"), F.col("code2_b")
    return out.select(
        *STACK, "item", "unit",
        F.when(pair, F.col("value")).alias("value"),
        "limit",
        F.when(both_ok & F.col("limit").isNotNull(), "ok")
        .when(both_ok, "not_monitored")
        .when(pair, "other_code")
        .when(F.col("n_num") == 1, "partial")
        .otherwise("invalid").alias("status"),
        F.col("slot").alias("ts_kst"),
        ratio.alias("ratio"),
        (F.col("slot") - F.expr("INTERVAL 1 HOUR")).alias("ts_local"),
        F.when(a == b, a).otherwise(F.concat(a, F.lit("|"), b)).alias("code2"),
        F.coalesce(((a == "NA10") & (b == "NA10") & (ratio >= 1)) | ((a == "NA11") & (b == "NA11") & (ratio < 1)), F.lit(False)).alias("flag_code_ratio_mismatch"),
    ).select(*COLUMNS)


def spark_session(app: str = "smokestack_guard_tw_cems", master: str = "local[*]") -> SparkSession:
    return (
        SparkSession.builder.appName(app)
        .master(master)
        .config("spark.sql.session.timeZone", "UTC")  # timestamps are wall clocks
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")  # a rerun replaces only the months it wrote
        .getOrCreate()
    )


def read_raw(spark: SparkSession, source: str) -> DataFrame:
    return spark.read.option("primitivesAsString", "true").json(source)


def build(spark: SparkSession, source: str, output: str) -> None:
    silver = to_silver(read_raw(spark, source))
    (
        silver.withColumn("year", F.date_format("ts_local", "yyyy")).withColumn("month", F.date_format("ts_local", "MM"))
        .write.mode("overwrite").partitionBy("year", "month").parquet(output)
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Taiwan CEMS 15-minute JSON Lines -> silver parquet (Spark)")
    p.add_argument("source")
    p.add_argument("output")
    a = p.parse_args()
    build(spark_session(), a.source, a.output)


if __name__ == "__main__":
    main()
