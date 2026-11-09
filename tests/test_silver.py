import unittest

import pandas as pd

from smokestack_guard.silver import ktms


class KtmsSilverTests(unittest.TestCase):
    def test_status_dedupe_and_ratio(self):
        def item(snapshot, dt, nox, limit="50"):
            row = dict.fromkeys([f"{i}_{s}" for i in ktms.ITEMS for s in ("mesure_value", "exhst_perm_stdr_value")])
            return row | {"area_nm": "A", "fact_manage_nm": "F", "stack_code": "1", "mesure_dt": dt, "snapshot": snapshot,
                          "nox_mesure_value": nox, "nox_exhst_perm_stdr_value": limit}

        df = pd.DataFrame([
            item(0, "2026-11-02 12:30", "측정자료확인중"),
            item(1, "2026-11-02 12:30", "25"),  # later snapshot fills in the value
            item(1, "2026-11-02 13:00", "미수신"),
        ])
        out = ktms.to_silver(df)
        self.assertEqual(len(out), 2)
        first, second = out.iloc[0], out.iloc[1]
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["ratio"], 0.5)
        self.assertEqual(second["status"], "no_signal")
        self.assertTrue(pd.isna(second["value"]))

    def test_missing_limit_marks_item_as_not_monitored(self):
        df = pd.DataFrame([
            {
                "area_nm": "A",
                "fact_manage_nm": "F",
                "stack_code": "1",
                "mesure_dt": "2026-11-02 12:30",
                "snapshot": 1,
                "nox_mesure_value": "25",
                "nox_exhst_perm_stdr_value": None,
            }
        ])
        out = ktms.to_silver(df)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["status"], "not_monitored")
        self.assertTrue(pd.isna(out.iloc[0]["ratio"]))

    @staticmethod
    def fake_s3(snapshots):
        import gzip
        import json

        class Paginator:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for k in sorted(snapshots) if k.startswith(Prefix)]}

        class Client:
            def get_paginator(self, name):
                return Paginator()

            def get_object(self, Bucket, Key):
                body = gzip.compress(json.dumps({"response": {"body": {"items": snapshots[Key]}}}).encode())
                return {"Body": type("B", (), {"read": lambda self: body})()}

        return Client()

    def test_read_bronze_reads_only_the_ingest_date_range(self):
        from datetime import date

        def key(day, hour):
            return f"tms_cleansys/ingest_date={day}/hour={hour:02d}/run_ts={day}T{hour:02d}0000Z/snapshot.json.gz"

        stack = {"area_nm": "A", "fact_manage_nm": "F", "stack_code": "1", "mesure_dt": "2026-11-02 12:30"}
        s3 = self.fake_s3({
            key("2026-11-01", 1): [stack | {"nox_mesure_value": "1"}],
            key("2026-11-02", 1): [stack | {"nox_mesure_value": "2"}],
            key("2026-11-02", 2): [stack | {"nox_mesure_value": "3"}],
            key("2026-11-03", 1): [stack | {"nox_mesure_value": "4"}],
            "tms_cleansys/ingest_date=2026-11-02/hour=01/run_ts=x/snapshot.meta.json": [],
        })
        df = ktms.read_bronze("b", date(2026, 11, 2), date(2026, 11, 2), s3=s3)
        self.assertEqual(df["nox_mesure_value"].tolist(), ["2", "3"])
        self.assertEqual(df["snapshot"].tolist(), [0, 1])
        self.assertEqual(len(ktms.read_bronze("b", s3=s3)), 4)
        self.assertEqual(len(ktms.read_bronze("b", date(2026, 11, 2), s3=s3)), 2)
        self.assertTrue(ktms.read_bronze("b", date(2026, 11, 4), s3=s3).empty)

    def test_quality_counts_rows_stacks_status_and_duplicates(self):
        stack = {"area_nm": "A", "fact_manage_nm": "F", "nox_exhst_perm_stdr_value": "50"}
        df = pd.DataFrame([
            stack | {"stack_code": "1", "mesure_dt": "2026-11-02 12:30", "snapshot": 0, "nox_mesure_value": "25"},
            stack | {"stack_code": "2", "mesure_dt": "2026-11-02 12:30", "snapshot": 0, "nox_mesure_value": "미수신"},
            stack | {"stack_code": "1", "mesure_dt": "2026-11-03 00:00", "snapshot": 1, "nox_mesure_value": "30"},
        ])
        q = ktms.quality(ktms.to_silver(df), snapshots=2)
        self.assertEqual((q["snapshots"], q["rows"], q["stacks"], q["duplicate_keys"]), (2, 3, 2, 0))
        self.assertEqual(q["status"], {"ok": 2, "no_signal": 1})
        self.assertEqual(q["rows_per_day"], {"2026-11-02": 2, "2026-11-03": 1})

    def test_conflicting_rows_with_the_same_key_in_one_snapshot_are_ambiguous(self):
        base = {"area_nm": "A", "fact_manage_nm": "F", "stack_code": "1", "mesure_dt": "2026-11-02 12:30", "snapshot": 0,
                "tsp_exhst_perm_stdr_value": "50", "nox_exhst_perm_stdr_value": "50"}
        df = pd.DataFrame([
            base | {"tsp_mesure_value": "미수신", "nox_mesure_value": None},
            base | {"tsp_mesure_value": "0.43", "nox_mesure_value": "25"},  # nox is reported by one row only
            base | {"stack_code": "2", "tsp_mesure_value": "5", "nox_mesure_value": "7"},
            base | {"stack_code": "2", "tsp_mesure_value": "5", "nox_mesure_value": "7"},  # identical rows are not a conflict
        ])
        out = ktms.to_silver(df).set_index(["stack_code", "item"])
        self.assertEqual(out.loc[("1", "tsp"), "status"], "ambiguous")
        self.assertTrue(pd.isna(out.loc[("1", "tsp"), "value"]) and pd.isna(out.loc[("1", "tsp"), "ratio"]))
        self.assertEqual(out.loc[("1", "nox"), "status"], "ok")
        self.assertEqual(out.loc[("2", "tsp"), "status"], "ok")

    def test_partitions_are_written_per_ts_date_inside_the_window_and_overwritten(self):
        import tempfile
        from datetime import date
        from pathlib import Path

        def rows(*days, status="ok"):
            return pd.DataFrame({"ts_kst": pd.to_datetime([f"{d} 12:00" for d in days]), "status": status})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = ktms.write_partitions(rows("2026-11-01", "2026-11-02", "2026-11-03"), root, date(2026, 11, 2), date(2026, 11, 3))
            self.assertEqual(written, [date(2026, 11, 2), date(2026, 11, 3)])
            self.assertFalse((root / "ktms" / "ts_date=2026-11-01").exists())
            ktms.write_partitions(rows("2026-11-02", status="stopped"), root, date(2026, 11, 2), date(2026, 11, 3))
            again = pd.read_parquet(root / "ktms" / "ts_date=2026-11-02" / "part.parquet")
            self.assertEqual(again["status"].tolist(), ["stopped"])

    def test_later_snapshot_wins_when_dates_are_split(self):
        from datetime import date

        stack = {"area_nm": "A", "fact_manage_nm": "F", "stack_code": "1", "mesure_dt": "2026-11-02 12:30",
                 "nox_exhst_perm_stdr_value": "50"}
        s3 = self.fake_s3({
            "tms_cleansys/ingest_date=2026-11-02/hour=04/run_ts=a/snapshot.json.gz": [stack | {"nox_mesure_value": "측정자료확인중"}],
            "tms_cleansys/ingest_date=2026-11-02/hour=05/run_ts=b/snapshot.json.gz": [stack | {"nox_mesure_value": "25"}],
        })
        out = ktms.to_silver(ktms.read_bronze("b", date(2026, 11, 2), date(2026, 11, 2), s3=s3))
        self.assertEqual(out.iloc[0]["status"], "ok")
        self.assertEqual(out.iloc[0]["ratio"], 0.5)


if __name__ == "__main__":
    unittest.main()


class TwCemsSilverTests(unittest.TestCase):
    @staticmethod
    def row(t, v, code="NA10", item="923", unit="ppm", std="100", polno="P1"):
        return {"cno": "X1", "polno": polno, "item": item, "m_time": t, "m_value": v, "std": std, "std_s": "電力", "unit": unit, "code2": code, "abbr": "TestCo", "epb_county": "Taipei"}

    def silver(self, *rows):
        from smokestack_guard.silver import tw_cems

        return tw_cems.to_silver(pd.DataFrame(list(rows)))

    def test_build_accepts_monthly_jsonl(self):
        import json
        import tempfile
        from pathlib import Path

        from smokestack_guard.silver import tw_cems

        rows = [self.row("2026-11-02T08:00:00", "40"), self.row("2026-11-02T08:15:00", "50")]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "2026-11.jsonl"
            source.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            result = tw_cems.build(source, Path(tmp) / "silver")
            self.assertEqual(pd.read_parquet(result).shape[0], 1)

    def test_pair_becomes_one_ok_row_in_ktms_contract(self):
        out = self.silver(self.row("2026-11-02T08:00:00", "40"), self.row("2026-11-02T08:15:00", "50", code="NA11"))
        self.assertEqual(len(out), 1)
        r = out.iloc[0]
        self.assertEqual((r["stack_code"], r["item"], r["status"]), ("X1-P1", "nox", "ok"))
        self.assertEqual(r["ts_kst"], pd.Timestamp("2026-11-02 09:00"))  # Taipei 08:00 = KST 09:00
        self.assertEqual(r["ts_local"], pd.Timestamp("2026-11-02 08:00"))
        self.assertEqual((r["value"], r["limit"], r["ratio"]), (45, 100, 0.45))
        self.assertEqual(r["code2"], "NA10|NA11")

    def test_mixed_timestamp_separators_pair_up(self):
        out = self.silver(self.row("2026-11-02T08:00:00", "40"), self.row("2026-11-02 08:15:00", "50"))  # a month can mix "T" and space
        self.assertEqual(out.iloc[0]["status"], "ok")

    def test_every_item_is_converted_with_its_unit(self):
        rows = [self.row("2026-11-02T08:00:00", "5", item="924"), self.row("2026-11-02T08:15:00", "5", item="924"),  # CO
                self.row("2026-11-02T08:00:00", "4.5", item="936", unit="%", std=""), self.row("2026-11-02T08:15:00", "5.5", item="936", unit="%", std="")]
        out = self.silver(*rows).set_index("item")
        self.assertEqual(set(out.index), {"co", "o2"})
        self.assertEqual((out.loc["co", "status"], out.loc["co", "unit"]), ("ok", "ppm"))
        self.assertEqual((out.loc["o2", "status"], out.loc["o2", "value"], out.loc["o2", "unit"]), ("not_monitored", 5.0, "%"))
        self.assertTrue(pd.isna(out.loc["o2", "ratio"]))
        self.assertEqual(self.silver(self.row("2026-11-02T08:00:00", "1", item="999"))["item"].iloc[0], "999")

    def test_code_ratio_mismatch_is_flagged(self):
        out = self.silver(self.row("2026-11-02T08:00:00", "120"), self.row("2026-11-02T08:15:00", "130"))
        self.assertTrue(out.iloc[0]["flag_code_ratio_mismatch"])
        self.assertEqual(out.iloc[0]["status"], "ok")

    def test_one_numeric_row_leaves_value_empty(self):
        out = self.silver(self.row("2026-11-02T08:00:00", "40"), self.row("2026-11-02T08:15:00", ""))
        r = out.iloc[0]
        self.assertEqual(r["status"], "partial")
        self.assertTrue(pd.isna(r["value"]) and pd.isna(r["ratio"]))

    def test_other_codes_keep_their_value_but_are_not_ok(self):
        stopped = self.silver(self.row("2026-11-02T08:00:00", "80", code="FA10"), self.row("2026-11-02T08:15:00", "90", code="FA10"))
        self.assertEqual(stopped.iloc[0]["status"], "other_code")
        self.assertEqual((stopped.iloc[0]["value"], stopped.iloc[0]["ratio"]), (85, 0.85))
        mixed = self.silver(self.row("2026-11-02T08:00:00", "40", code="NB10"), self.row("2026-11-02T08:15:00", "50", code="AA11"))
        self.assertEqual((mixed.iloc[0]["status"], mixed.iloc[0]["code2"]), ("other_code", "NB10|AA11"))
        half = self.silver(self.row("2026-11-02T08:00:00", "40"), self.row("2026-11-02T08:15:00", "50", code="NA30"))
        self.assertEqual(half.iloc[0]["status"], "other_code")
        units = self.silver(self.row("2026-11-02T08:00:00", "11", unit="mg"), self.row("2026-11-02T08:15:00", "12", unit="mg"))
        self.assertEqual(units.iloc[0]["unit"], "mg")

    def test_duplicate_row_is_not_a_pair(self):
        r = self.row("2026-11-02T08:00:00", "40")
        out = self.silver(r, dict(r))
        self.assertEqual(out.iloc[0]["status"], "partial")

    def test_conflicting_rows_and_changed_limit_are_not_ok(self):
        conflict = self.silver(self.row("2026-11-02T08:00:00", "40"), self.row("2026-11-02T08:00:00", "41"), self.row("2026-11-02T08:15:00", "50"))
        self.assertEqual(conflict.iloc[0]["status"], "partial")
        moved = self.silver(self.row("2026-11-02T08:00:00", "40"), self.row("2026-11-02T08:15:00", "50", std="150"))
        self.assertEqual(moved.iloc[0]["status"], "invalid")

    def test_missing_limit_is_not_monitored(self):
        out = self.silver(self.row("2026-11-02T08:00:00", "40", std=None), self.row("2026-11-02T08:15:00", "50", std="0"))
        self.assertEqual(out.iloc[0]["status"], "not_monitored")

    def test_slots_split_across_input_chunks_still_pair(self):
        from smokestack_guard.silver import tw_cems

        a = tw_cems.prep(pd.DataFrame([self.row("2026-11-02T08:00:00", "40")]))
        b = tw_cems.prep(pd.DataFrame([self.row("2026-11-02T08:15:00", "50")]))
        out = tw_cems.to_silver(pd.concat([a, b], ignore_index=True))
        self.assertEqual(out.iloc[0]["status"], "ok")


class TwCemsMlReadyTests(unittest.TestCase):
    @staticmethod
    def _silver(ratios, start="2026-11-02 00:00", step="30min", times=None):
        times = times if times is not None else pd.date_range(start, periods=len(ratios), freq=step)
        return pd.DataFrame({"stack_code": "TW-X1-P1", "item_code": "CO", "measured_at": times, "measure_value": 1.0, "standard_value": 100.0, "ratio_pct": ratios})

    def test_entry_label_is_1_when_90_reached_at_30_or_60_min(self):
        from smokestack_guard.silver.ml_ready import to_ml_ready

        out = to_ml_ready(self._silver([10, 20, 95, 10, 10, 10, 10, 10])).set_index("ratio_pct", drop=False)
        self.assertEqual(out.loc[10].iloc[0]["label_entry_60m"], 1.0)
        self.assertEqual(out.loc[20]["label_entry_60m"], 1.0)
        self.assertTrue(pd.isna(out.loc[95]["label_entry_60m"]))
        self.assertEqual(out.iloc[3]["label_entry_60m"], 0.0)

    def test_gap_is_not_bridged_by_lag_or_label(self):
        from smokestack_guard.silver.ml_ready import to_ml_ready

        t0 = pd.Timestamp("2026-11-02 00:00")
        times = [t0 + pd.Timedelta(minutes=30 * i) for i in (0, 1, 2, 8, 9, 10)]  # 3-hour hole after the 3rd row
        out = to_ml_ready(self._silver([10, 20, 30, 95, 96, 97], times=times))
        self.assertEqual(len(out), 6)
        row = out[out["measured_at"] == pd.Timestamp("2026-11-02 04:00")].iloc[0]
        self.assertTrue(pd.isna(row["ratio_lag_30m"]))
        self.assertFalse(row["feature_valid"])
        first = out.iloc[0]
        self.assertEqual(first["label_ratio_60m"], 30)
        self.assertTrue(pd.isna(out.iloc[2]["label_ratio_60m"]))
        self.assertTrue(pd.isna(out.iloc[2]["label_entry_60m"]))

    def test_ml_ready_builds_feature_and_label_columns(self):
        from smokestack_guard.silver.ml_ready import to_ml_ready

        times = pd.date_range("2026-11-02 00:00", periods=8, freq="30min")
        df = pd.DataFrame([
            {"stack_code": "TW-X1-P1", "item_code": "CO", "measured_at": ts, "measure_value": 5.0, "standard_value": 150.0, "ratio_pct": 3.33}
            for ts in times
        ])
        df["ratio_pct"] = [3.33, 3.40, 3.10, 3.05, 2.90, 2.80, 2.70, 2.60]

        out = to_ml_ready(df)

        self.assertIn("ratio_lag_30m", out.columns)
        self.assertIn("headroom_pct", out.columns)
        self.assertIn("feature_valid", out.columns)
        self.assertIn("label_ratio_60m", out.columns)
        self.assertIn("label_entry_60m", out.columns)
        self.assertTrue(out["feature_valid"].iloc[5])
        self.assertAlmostEqual(out["ratio_lag_30m"].iloc[1], 3.33)
        self.assertAlmostEqual(out["label_ratio_60m"].iloc[0], 3.10)

    def test_trend_features_and_eligibility(self):
        from smokestack_guard.silver.ml_ready import to_ml_ready

        out = to_ml_ready(self._silver([10, 20, 15, 25, 35, 45, 50, 95])).iloc[5]
        self.assertEqual(out["ratio_diff_30m"], 10)
        self.assertEqual(out["ratio_acceleration"], 0)
        self.assertEqual(out["ratio_rolling_max_3h"], 45)
        self.assertEqual(out["ratio_range_3h"], 35)
        self.assertEqual(out["rise_count_3h"], 4)  # 20,15,25,35,45: one fall, four rises
        self.assertAlmostEqual(out["ratio_slope_3h"], 6.5714286)  # np.polyfit slope over 10,20,15,25,35,45
        self.assertAlmostEqual(out["ratio_rolling_mean_1h"], 40)
        self.assertEqual(out["day_of_week"], 0)
        self.assertTrue(out["classification_eligible"] and out["regression_eligible"])
        self.assertFalse(to_ml_ready(self._silver([95] * 8)).iloc[5]["classification_eligible"])

    def test_hour_features_use_the_taiwan_wall_clock(self):
        import math

        from smokestack_guard.silver.ml_ready import to_ml_ready

        out = to_ml_ready(self._silver([10], start="2026-11-02 08:00")).iloc[0]
        self.assertAlmostEqual(out["hour_sin"], math.sin(2 * math.pi * 8 / 24))
        self.assertIsNone(out["measured_at"].tzinfo)

    def test_ml_ready_takes_only_ok_nox_sox_ppm_from_silver(self):
        from smokestack_guard.silver import tw_cems
        from smokestack_guard.silver.ml_ready import to_ml_ready

        t = ["2026-11-02T08:00:00", "2026-11-02T08:15:00"]
        rows = [TwCemsSilverTests.row(t[0], "40"), TwCemsSilverTests.row(t[1], "50"),  # nox ok
                TwCemsSilverTests.row(t[0], "5", item="924"), TwCemsSilverTests.row(t[1], "5", item="924"),  # co ok, but not a target
                TwCemsSilverTests.row(t[0], "40", code="FA10", polno="P2"), TwCemsSilverTests.row(t[1], "50", code="FA10", polno="P2"),  # other_code
                TwCemsSilverTests.row(t[0], "4", item="936", unit="%", std=""), TwCemsSilverTests.row(t[1], "5", item="936", unit="%", std="")]
        out = to_ml_ready(tw_cems.to_silver(pd.DataFrame(rows)))
        self.assertEqual(list(out["item_code"]), ["nox"])
