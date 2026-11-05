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
        self.assertEqual(len(out), 2)  # only nox is monitored; sox..hf are null/null
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
        self.assertEqual(r["code2"], "NA10|NA11")  # mixed codes are fine and both are kept

    def test_co_is_not_a_target_and_code_ratio_mismatch_is_flagged(self):
        self.assertEqual(len(self.silver(self.row("2026-11-02T08:00:00", "5", item="924"), self.row("2026-11-02T08:15:00", "5", item="924"))), 0)
        out = self.silver(self.row("2026-11-02T08:00:00", "120"), self.row("2026-11-02T08:15:00", "130"))  # NA10 but over the limit
        self.assertTrue(out.iloc[0]["flag_code_ratio_mismatch"])
        self.assertEqual(out.iloc[0]["status"], "ok")  # flagged, not dropped

    def test_one_usable_row_leaves_value_empty(self):
        out = self.silver(self.row("2026-11-02T08:00:00", "40"), self.row("2026-11-02T08:15:00", "50", code="NA30"))
        r = out.iloc[0]
        self.assertEqual(r["status"], "partial")
        self.assertTrue(pd.isna(r["value"]) and pd.isna(r["ratio"]))  # never filled

    def test_unusable_rows_and_units(self):
        out = self.silver(
            self.row("2026-11-02T08:00:00", "80", code="FA10"), self.row("2026-11-02T08:15:00", "90", code="FA10"),  # not operating
            self.row("2026-11-02T08:30:00", "11", unit="mg"), self.row("2026-11-02T08:45:00", "12", item="999"),  # dropped
        )
        self.assertEqual(list(out["status"]), ["invalid"])

    def test_duplicate_row_is_not_a_pair(self):
        r = self.row("2026-11-02T08:00:00", "40")
        out = self.silver(r, dict(r))  # same :00 row twice, no :15
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
        # t=10 -> +60 is 95 (entry); t=20 -> already... 20 is below, +30 is 95 (entry); t=95 -> already above, not a new entry
        self.assertEqual(out.loc[10].iloc[0]["label_entry_60m"], 1.0)
        self.assertEqual(out.loc[20]["label_entry_60m"], 1.0)
        self.assertTrue(pd.isna(out.loc[95]["label_entry_60m"]))
        self.assertEqual(out.iloc[3]["label_entry_60m"], 0.0)  # 10 -> 10, 10: no entry

    def test_gap_is_not_bridged_by_lag_or_label(self):
        from smokestack_guard.silver.ml_ready import to_ml_ready

        t0 = pd.Timestamp("2026-11-02 00:00")
        times = [t0 + pd.Timedelta(minutes=30 * i) for i in (0, 1, 2, 8, 9, 10)]  # 3-hour hole after the 3rd row
        out = to_ml_ready(self._silver([10, 20, 30, 95, 96, 97], times=times))
        self.assertEqual(len(out), 6)  # grid rows are not leaked into the output
        row = out[out["measured_at"] == pd.Timestamp("2026-11-02 04:00", tz="UTC")].iloc[0]  # first row after the hole
        self.assertTrue(pd.isna(row["ratio_lag_30m"]))  # not 30.0 from before the hole
        self.assertFalse(row["feature_valid"])
        first = out.iloc[0]
        self.assertEqual(first["label_ratio_60m"], 30)
        self.assertTrue(pd.isna(out.iloc[2]["label_ratio_60m"]))  # +60 min falls in the hole, not 96
        self.assertTrue(pd.isna(out.iloc[2]["label_entry_60m"]))  # undecidable, not 0

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

        out = to_ml_ready(self._silver([10, 20, 15, 25, 35, 45, 50, 95])).iloc[5]  # window 10..45 ending at t
        self.assertEqual(out["ratio_diff_30m"], 10)
        self.assertEqual(out["ratio_acceleration"], 0)  # +10 then +10
        self.assertEqual(out["ratio_rolling_max_3h"], 45)
        self.assertEqual(out["ratio_range_3h"], 35)
        self.assertEqual(out["rise_count_3h"], 4)  # 20,15,25,35,45: one fall, four rises
        self.assertAlmostEqual(out["ratio_slope_3h"], 6.5714286)  # np.polyfit slope over 10,20,15,25,35,45
        self.assertAlmostEqual(out["ratio_rolling_mean_1h"], 40)
        self.assertEqual(out["day_of_week"], 0)
        self.assertTrue(out["classification_eligible"] and out["regression_eligible"])
        self.assertFalse(to_ml_ready(self._silver([95] * 8)).iloc[5]["classification_eligible"])  # already >= 90
