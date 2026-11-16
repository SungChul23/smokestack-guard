import unittest

import numpy as np
import pandas as pd

from smokestack_guard.silver.ml_ready import to_ml_ready
from smokestack_guard.silver.ml_ready_inference import INFERENCE_COLUMNS, to_inference_features


def silver(stack="S", n=40, limits=None, drop=(), seed=0):
    rng = np.random.default_rng(seed)
    times = pd.date_range("2026-11-02 00:00", periods=n, freq="30min")
    ratio = np.clip(50 + np.cumsum(rng.normal(0, 8, n)), 1, 150)
    df = pd.DataFrame({"stack_code": stack, "item_code": "nox", "measured_at": times, "measure_value": ratio,
                       "standard_value": 100.0 if limits is None else limits, "ratio_pct": ratio})
    return df.drop(index=list(drop)).reset_index(drop=True)


class InferenceFeatureTests(unittest.TestCase):
    def test_latest_slot_features_match_full_history(self):
        df = silver(drop=[7, 8])
        full = to_ml_ready(df).set_index("measured_at")
        cols = [c for c in INFERENCE_COLUMNS if c not in ("inference_eligible", "measured_at", "data_source")]
        for end in (12, 20, 33, 39):
            t = pd.date_range("2026-11-02", periods=40, freq="30min")[end]
            window = df[(df.measured_at > t - pd.Timedelta(hours=3)) & (df.measured_at <= t)]
            got = to_inference_features(window).iloc[0]
            want = full.loc[t]
            pd.testing.assert_series_equal(got[cols].astype(object), want[cols].astype(object), check_names=False)

    def test_eligible_only_with_six_consecutive_slots_and_one_limit(self):
        ok = to_inference_features(silver(n=10))
        self.assertTrue(ok.inference_eligible.iloc[0])
        gap = to_inference_features(silver(n=10, drop=[7]))
        self.assertFalse(gap.inference_eligible.iloc[0])
        changed = to_inference_features(silver(n=10, limits=[100.0] * 7 + [50.0] * 3))  # limit changes 3 slots ago
        self.assertTrue(changed.feature_valid.iloc[0])
        self.assertFalse(changed.inference_eligible.iloc[0])
        old_change = to_inference_features(silver(n=12, limits=[100.0] * 2 + [50.0] * 10))  # change is older than 150 min
        self.assertTrue(old_change.inference_eligible.iloc[0])

    def test_only_stacks_with_the_as_of_slot_are_returned(self):
        both = pd.concat([silver("A", n=10), silver("B", n=9, seed=1)], ignore_index=True)
        self.assertEqual(to_inference_features(both).stack_code.tolist(), ["A"])
        t = silver("B", n=9).measured_at.max()
        self.assertEqual(sorted(to_inference_features(both, as_of=t).stack_code), ["A", "B"])

    def test_empty_input(self):
        self.assertEqual(list(to_inference_features(silver(n=10).iloc[0:0]).columns), INFERENCE_COLUMNS)


if __name__ == "__main__":
    unittest.main()
