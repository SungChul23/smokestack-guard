"""Spark and pandas silver must agree. Skipped where PySpark/Java is not usable."""
import unittest

import pandas as pd

try:
    from pyspark.sql.types import StringType, StructField, StructType

    from smokestack_guard.silver import tw_cems, tw_cems_spark

    SPARK = tw_cems_spark.spark_session(master="local[2]")
    SPARK.range(1).count()
except Exception as exc:  # noqa: BLE001
    SPARK, SKIP = None, str(exc)[:80]

KEY = ["stack_code", "item", "unit", "ts_kst"]


def row(t, v, code="NA10", item="923", unit="ppm", std="100", polno="P1"):
    return {"cno": "X1", "polno": polno, "item": item, "m_time": t, "m_value": v, "std": std, "std_s": "電力", "unit": unit, "code2": code, "abbr": "TestCo", "epb_county": "Taipei"}


def cases():
    d = "2026-11-02T"
    rows = []
    rows += [row(d + "08:00:00", "40", polno="ok"), row(d + "08:15:00", "50", code="NA11", polno="ok")]  # ok
    rows += [row(d + "08:00:00", "120", polno="mm"), row(d + "08:15:00", "130", polno="mm")]  # mismatch flag
    rows += [row(d + "08:00:00", "80", code="FA10", polno="fa"), row(d + "08:15:00", "90", code="FA10", polno="fa")]  # other_code
    rows += [row(d + "08:00:00", "40", code="NB10", polno="nb"), row(d + "08:15:00", "50", code="AA11", polno="nb")]  # other_code
    rows += [row(d + "08:00:00", "40", polno="p1"), row(d + "08:15:00", "", polno="p1")]  # empty value
    rows += [row(d + "08:00:00", "40", polno="p2"), row(d + "08:15:00", "nan", polno="p2")]  # "nan"
    rows += [row(d + "08:00:00", "40", polno="du"), row(d + "08:00:00", "40", polno="du")]  # duplicate
    rows += [row(d + "08:00:00", "40", polno="cf"), row(d + "08:00:00", "41", polno="cf"), row(d + "08:15:00", "50", polno="cf")]  # conflict
    rows += [row(d + "08:00:00", "40", polno="lm"), row(d + "08:15:00", "50", std="150", polno="lm")]  # limit changed
    rows += [row(d + "08:00:00", "40", std=None, polno="nl"), row(d + "08:15:00", "50", std="0", polno="nl")]  # no limit
    rows += [row(d + "08:00:00", "4.5", item="936", unit="%", std="", polno="o2"), row(d + "08:15:00", "5.5", item="936", unit="%", std="", polno="o2")]
    rows += [row(d + "08:00:00", "5", item="924", polno="co"), row(d + "08:15:00", "5", item="924", polno="co")]
    rows += [row(d + "08:00:00", "11", unit="mg", polno="un"), row(d + "08:15:00", "12", unit="mg", polno="un")]  # other unit
    rows += [row(d + "08:00:00", "1", item="999", polno="uk")]  # unknown item
    rows += [row("2026-11-02 08:00", "40", polno="fm"), row("2026-11-02T08:15:00", "50", polno="fm")]  # time formats
    rows += [row(d + "08:30:00", "60", polno="sl"), row(d + "08:45:00", "70", polno="sl"), row(d + "09:00:00", "10", polno="sl")]  # two slots
    rows += [row(d + "08:00:00", "40", code="NA20", polno="bad"), row(d + "08:15:00", "50", code="NA30", polno="bad")]
    return rows


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df[tw_cems.COLUMNS].copy()
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith("string"):
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df.sort_values(KEY).reset_index(drop=True)


@unittest.skipIf(SPARK is None, "PySpark is not usable here")
class SparkParityTests(unittest.TestCase):
    def test_every_case_matches_pandas(self):
        rows = cases()
        expected = normalize(tw_cems.to_silver(pd.DataFrame(rows)))
        keys = list(rows[0])
        raw = SPARK.createDataFrame([tuple(r[k] for k in keys) for r in rows], StructType([StructField(k, StringType()) for k in keys]))
        actual = normalize(tw_cems_spark.to_silver(raw).toPandas())
        self.assertEqual(set(expected["status"]), {"ok", "not_monitored", "other_code", "partial", "invalid"})
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, check_exact=False, rtol=1e-9)


if __name__ == "__main__":
    unittest.main()
