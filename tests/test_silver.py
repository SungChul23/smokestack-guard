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
    def test_build_accepts_monthly_jsonl(self):
        from pathlib import Path
        import tempfile

        from smokestack_guard.silver import tw_cems

        rows = [
            {"cno": "X1", "polno": "P1", "item": "923", "m_time": "2026-11-02T08:00:00", "m_value": "40", "std": "100", "std_s": "電力", "unit": "ppm", "code2": "NA10"},
            {"cno": "X1", "polno": "P1", "item": "923", "m_time": "2026-11-02T08:15:00", "m_value": "50", "std": "100", "std_s": "電力", "unit": "ppm", "code2": "NA10"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "2026-11.jsonl"
            source.write_text("\n".join(__import__('json').dumps(r) for r in rows) + "\n", encoding="utf-8")
            out_dir = Path(tmp) / "silver"
            result = tw_cems.build(source, out_dir)
            self.assertTrue(result.exists())
            self.assertEqual(pd.read_parquet(result).shape[0], 1)

    def test_pairs_into_30min_utc_and_filters_state(self):
        from smokestack_guard.silver import tw_cems

        def row(t, v, code="NA10", item="923", unit="ppm", std="100"):
            return {"cno": "X1", "polno": "P1", "item": item, "m_time": t, "m_value": v, "std": std, "std_s": "電力", "unit": unit, "code2": code}

        df = pd.DataFrame([
            row("2026-11-02T08:00:00", "40"), row("2026-11-02T08:15:00", "50"),   # -> 00:00 UTC, mean 45
            row("2026-11-02T08:30:00", "60"), row("2026-11-02T08:45:00", "70", code="NA30"),  # invalid -> slot empty
            row("2026-11-02T09:00:00", "80", code="FA10"), row("2026-11-02T09:15:00", "90", code="FA10"),  # not operating
            row("2026-11-02T09:30:00", "11", unit="mg"), row("2026-11-02T09:45:00", "12", item="999"),  # dropped
        ])
        out = tw_cems.to_silver(df)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["stack_code"], "TW-X1-P1")
        self.assertEqual(out.iloc[0]["measured_at"], pd.Timestamp("2026-11-02 00:00"))
        self.assertEqual(out.iloc[0]["measure_value"], 45)
        self.assertEqual(out.iloc[0]["ratio_pct"], 45)

    def test_slot_with_missing_standard_is_dropped(self):
        from smokestack_guard.silver import tw_cems

        def row(t, v, item="923", unit="ppm", std="100"):
            return {"cno": "X1", "polno": "P1", "item": item, "m_time": t, "m_value": v, "std": std, "std_s": "電力", "unit": unit, "code2": "NA10"}

        df = pd.DataFrame([
            row("2026-11-02T08:00:00", "40"),
            row("2026-11-02T08:15:00", "50", std=None),
        ])
        out = tw_cems.to_silver(df)
        self.assertEqual(len(out), 0)


class TwCemsMlReadyTests(unittest.TestCase):
    def test_ml_ready_builds_feature_and_label_columns(self):
        from smokestack_guard.silver.ml_ready import to_ml_ready

        times = pd.date_range("2026-11-02 00:00", periods=8, freq="30min")
        df = pd.DataFrame([
            {"stack_code": "TW-X1-P1", "item_code": "CO", "measured_at": ts, "measure_value": 5.0, "standard_value": 150.0, "ratio_pct": 3.33}
            for ts in times
        ])
        df["ratio_pct"] = [3.33, 3.40, 3.10, 3.05, 2.90, 2.80, 2.70, 2.60]

        out = to_ml_ready(df)

        self.assertIn("lag_30m", out.columns)
        self.assertIn("headroom_pct", out.columns)
        self.assertIn("feature_valid", out.columns)
        self.assertIn("label_ratio_60m", out.columns)
        self.assertIn("label_entry_60m", out.columns)
        self.assertTrue(out["feature_valid"].iloc[5])
        self.assertAlmostEqual(out["lag_30m"].iloc[1], 3.33)
        self.assertAlmostEqual(out["label_ratio_60m"].iloc[0], 3.10)
