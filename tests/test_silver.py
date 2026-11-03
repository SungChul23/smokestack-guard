import unittest

import pandas as pd

from smokestack_guard.silver import ecmps, ktms


def _ecmps_row(param, value, modc="01", component="C1", unit="1", hour="0"):
    return {
        "facility_id": "10", "unit_id": unit, "stack_pipe_id": None, "monitor_plan_id": "p", "date": "2026-07-01",
        "hour": hour, "parameter_code": param, "unadjusted_hourly_value": value, "modc_code": modc,
        "operating_time": "1", "component_id": component,
    }


class EcmpsSilverTests(unittest.TestCase):
    def test_pivots_hour_and_prefers_primary_monitor(self):
        df = pd.DataFrame([
            _ecmps_row("NOXC", "50", modc="02", component="BACKUP"),
            _ecmps_row("NOXC", "40", modc="01", component="MAIN"),
            _ecmps_row("FLOW", "900"),
            _ecmps_row("NOXC", "41", hour="1"),
        ])
        out = ecmps.to_silver(df).sort_values("ts_local")
        self.assertEqual(len(out), 2)
        self.assertEqual(out.iloc[0]["NOXC"], 40)
        self.assertEqual(out.iloc[0]["NOXC_modc"], "01")
        self.assertEqual(out.iloc[0]["FLOW"], 900)
        self.assertEqual(out.iloc[1]["ts_local"], pd.Timestamp("2026-07-01 01:00"))
        self.assertTrue(out["operating"].all())

    def test_stack_rows_use_stack_pipe_as_entity(self):
        row = _ecmps_row("SO2C", "3", unit=None) | {"stack_pipe_id": "CS001"}
        self.assertEqual(ecmps.to_silver(pd.DataFrame([row])).iloc[0]["entity_id"], "CS001")


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


if __name__ == "__main__":
    unittest.main()
