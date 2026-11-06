"""Compare the Spark and pandas silver on one raw JSON Lines file: python scripts/validate_spark_parity.py file.jsonl [--master local[4]]. Exit 1 on any mismatch."""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from smokestack_guard.silver import tw_cems, tw_cems_spark

KEY = ["stack_code", "item", "unit", "ts_kst"]


def pandas_silver(source: str) -> pd.DataFrame:
    raw = pd.concat([tw_cems.prep(c) for c in pd.read_json(source, lines=True, chunksize=250_000, dtype=False)], ignore_index=True)
    return tw_cems.to_silver(raw)


def spark_silver(source: str, master: str) -> pd.DataFrame:
    spark = tw_cems_spark.spark_session(master=master)
    return tw_cems_spark.to_silver(tw_cems_spark.read_raw(spark, source)).toPandas()


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df[tw_cems.COLUMNS].copy()
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith("string"):
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df.sort_values(KEY).reset_index(drop=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("--master", default="local[*]")
    a = p.parse_args()
    expected, actual = normalize(pandas_silver(a.source)), normalize(spark_silver(a.source, a.master))
    print(f"rows pandas={len(expected):,} spark={len(actual):,}")
    print("status pandas:", expected["status"].value_counts().to_dict())
    print("status spark :", actual["status"].value_counts().to_dict())
    if len(expected) != len(actual):
        merged = expected[KEY].merge(actual[KEY], how="outer", on=KEY, indicator=True)
        print("only in one side:", merged["_merge"].value_counts().to_dict())
        return 1
    bad = {}
    for c in tw_cems.COLUMNS:
        x, y = expected[c], actual[c]
        same = (x == y) | (x.isna() & y.isna())
        if x.dtype.kind == "f" or y.dtype.kind == "f":
            same = same | ((x - y).abs() <= 1e-9 * x.abs().clip(lower=1))
        if not same.all():
            bad[c] = int((~same).sum())
    print("mismatching rows per column:", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
