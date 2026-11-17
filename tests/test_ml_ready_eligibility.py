import unittest

import pandas as pd

from smokestack_guard.silver.ml_ready import QUALITY_POLICY_VERSION, to_ml_ready


def silver(ratios, limits, drop=()):
    times = pd.date_range("2026-11-02 00:00", periods=len(ratios), freq="30min")
    df = pd.DataFrame({"stack_code": "S", "item_code": "NOx", "measured_at": times, "measure_value": 1.0,
                       "standard_value": limits, "ratio_pct": ratios})
    return df.drop(index=list(drop)).reset_index(drop=True)


def eligible(out, col):
    return [i for i, ok in enumerate(out[col]) if ok]


class EligibilityTests(unittest.TestCase):
    def test_limit_change_excludes_rows_whose_window_contains_it(self):
        # limit changes at slot 8: rows 6..12 see it (150 min back .. 60 min ahead)
        out = to_ml_ready(silver([10.0] * 16, [100.0] * 8 + [50.0] * 8))
        self.assertEqual(len(out), 16)  # rows and feature_valid are kept
        self.assertEqual(eligible(out, "classification_eligible"), [5, 13])
        self.assertEqual(eligible(out, "regression_eligible"), [5, 13])
        self.assertTrue(out["feature_valid"].iloc[6:13].all())

    def test_no_change_means_no_exclusion(self):
        out = to_ml_ready(silver([10.0] * 16, [100.0] * 16))
        self.assertEqual(eligible(out, "classification_eligible"), list(range(5, 14)))

    def test_change_across_a_gap_still_excludes_rows_that_see_both_limits(self):
        # slot 8 missing: slot 7 (limit 100) predicts slot 9 (limit 50), so row 7 must not be trained on
        out = to_ml_ready(silver([10.0] * 16, [100.0] * 9 + [50.0] * 7, drop=[8]))
        self.assertEqual(eligible(out, "regression_eligible"), [5])

    def test_regression_includes_rows_already_at_or_above_90(self):
        out = to_ml_ready(silver([95.0] * 10, [100.0] * 10))
        self.assertEqual(eligible(out, "regression_eligible"), list(range(5, 8)))
        self.assertEqual(out["classification_eligible"].sum(), 0)  # classification unchanged

    def test_quality_policy_version_is_v2(self):
        self.assertEqual(QUALITY_POLICY_VERSION, "v2")
        self.assertEqual(set(to_ml_ready(silver([10.0] * 8, [100.0] * 8))["quality_policy_version"]), {"v2"})

    def test_data_source_default_and_override(self):
        s = silver([10.0] * 8, [100.0] * 8)  # 이미 정규화된 입력이라 출처를 알 수 없다 → 직접 지정해야 한다
        self.assertEqual(set(to_ml_ready(s)["data_source"]), {None})
        self.assertEqual(set(to_ml_ready(s, "ktms_synth")["data_source"]), {"ktms_synth"})


if __name__ == "__main__":
    unittest.main()
