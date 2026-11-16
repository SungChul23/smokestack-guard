import unittest

import numpy as np
import pandas as pd

from smokestack_guard.silver.ml_ready import to_ml_ready
from smokestack_guard.silver.ml_ready_check import check


def table(source="ktms_synth"):
    times = pd.date_range("2026-11-02 00:00", periods=40, freq="30min")
    ratio = np.r_[np.linspace(10, 80, 20), np.linspace(85, 95, 10), np.linspace(60, 20, 10)]
    df = pd.DataFrame({"stack_code": "S", "item_code": "nox", "measured_at": times, "measure_value": ratio, "standard_value": 100.0, "ratio_pct": ratio})
    return to_ml_ready(df.drop(index=[12]), data_source=source)  # one missing slot


class MlReadyCheckTests(unittest.TestCase):
    def test_valid_table_passes(self):
        self.assertEqual(check(table(), "ktms_synth"), [])

    def test_wrong_or_mixed_data_source_fails(self):
        self.assertTrue(check(table(), "ktms"))
        mixed = table()
        mixed.loc[0, "data_source"] = "tw_cems"
        self.assertTrue(any("data_source" in f for f in check(mixed)))

    def test_tampered_label_or_feature_is_caught_by_recompute(self):
        for col in ("label_entry_60m", "ratio_lag_60m"):
            t = table()
            i = t.index[t[col].notna()][10]
            t.loc[i, col] = t.loc[i, col] + 1
            self.assertTrue(any(col in f for f in check(t)), col)

    def test_missing_column_and_shared_stack_fail(self):
        self.assertTrue(check(table().drop(columns=["ratio_slope_3h"])))
        self.assertTrue(any("겹친다" in f for f in check(table(), real_stacks={"S"})))


if __name__ == "__main__":
    unittest.main()
