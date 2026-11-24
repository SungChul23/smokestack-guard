"""V2의 경계·품질·NaN 보존 및 학습/평가 연결만 검증한다. AWS 호출 없음."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEATURE_COLUMNS
from v2.contract import eligibility
from v2.dataset import ObservationIndex, prepare, fingerprint, local_files, normalize_times
from v2.evaluation import select_validation_points, evaluate_rows, warning_bundles, event_report
from v2.train_entrypoint import fit_candidate, SCALES


def fixture(start="2024-01-01"):
    """테스트용 관측만 생성한다. 원본 데이터·모델을 사용하지 않는다."""
    ratio = np.array([10, 20, 30, 40, 50, 95, 30, 40, 50, 60, 70, 95, 30, 40.], float)
    times = pd.date_range(start, periods=len(ratio), freq="30min")
    rows = []
    for i, value in enumerate(ratio):
        past = np.array([ratio[i-j] if i >= j else np.nan for j in range(6)])
        full = np.isfinite(past).all()
        next_values = ratio[i+1:i+3]
        reached = (next_values >= 90).any()
        known = reached or len(next_values) == 2
        label = float(reached) if value < 90 and known else np.nan
        row = {c: np.nan for c in FEATURE_COLUMNS}
        row.update(ratio_pct=value, headroom_pct=90-value,
                   ratio_diff_30m=past[0]-past[1],
                   ratio_diff_60m=past[0]-past[2],
                   ratio_acceleration=past[0]-2*past[1]+past[2],
                   ratio_rolling_mean_1h=np.mean(past[:2]),
                   hour_sin=0., hour_cos=1., month_sin=0., month_cos=1., day_of_week=0.)
        for j in range(1, 6):
            row[f"ratio_lag_{j*30}m"] = past[j]
        if full:
            row.update(ratio_rolling_mean_3h=past.mean(), ratio_rolling_std_3h=past.std(ddof=1),
                       ratio_rolling_max_3h=past.max(), ratio_range_3h=np.ptp(past),
                       ratio_slope_3h=float(past[::-1] @ (np.arange(6)-2.5)/17.5),
                       rise_count_3h=float((np.diff(past[::-1])>0).sum()))
        row.update(stack_code="fixture", item_code="nox", measured_at=times[i],
                   measure_value=value, standard_value=100.,
                   label_entry_60m=label,
                   label_ratio_60m=ratio[i+2] if i+2<len(ratio) else np.nan,
                   feature_valid=bool(full), classification_eligible=bool(full and np.isfinite(label)),
                   regression_eligible=False, feature_version="v1", label_version="v1",
                   quality_policy_version="v2", data_source="tw_cems")
        rows.append(row)
    return pd.DataFrame(rows)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def mask(self, data=None, index_data=None, confirmed=True):
        d = self.data if data is None else data
        return eligibility(d, ObservationIndex([d if index_data is None else index_data]),
                           normalized_silver_confirmed=confirmed)

    def test_baseline_and_source_unchanged(self):
        before = self.data.copy(deep=True)
        m = self.mask()
        np.testing.assert_array_equal(m.baseline, self.data.classification_eligible)
        pd.testing.assert_frame_equal(self.data, before)
        self.assertTrue(m.partial.any())

    def test_nan_preserved_and_full_feature_order(self):
        m = self.mask()
        x = self.data.loc[m.partial, list(FEATURE_COLUMNS)]
        self.assertTrue(x.isna().any().any())
        self.assertEqual(tuple(x.columns), FEATURE_COLUMNS)

    def test_exact_previous_observation_required(self):
        self.assertFalse(self.mask(self.data.iloc[[4]], self.data.drop(index=3)).partial.iloc[0])

    def test_positive_30min_without_60min(self):
        frame = self.data.iloc[[4]]
        self.assertTrue(self.mask(frame, self.data.drop(index=6)).partial.iloc[0])

    def test_unknown_or_inconsistent_label_excluded(self):
        d = self.data.copy()
        d.loc[4, "label_entry_60m"] = 0.
        self.assertFalse(self.mask(d).partial.iloc[4])
        d.loc[4, "label_entry_60m"] = np.nan
        self.assertFalse(self.mask(d).partial.iloc[4])

    def test_standard_change_future_and_past(self):
        for i in (0, 6):
            d = self.data.copy()
            d.loc[i, "standard_value"] = 101.
            self.assertFalse(self.mask(d).partial.iloc[4])

    def test_invalid_current_and_previous(self):
        for row, column, value in ((4, "standard_value", 0.), (3, "measure_value", np.nan)):
            d = self.data.copy()
            d.loc[row, column] = value
            self.assertFalse(self.mask(d).partial.iloc[4])

    def test_inf_rejected_not_replaced(self):
        d = self.data.copy()
        d.loc[4, "ratio_lag_150m"] = np.inf
        with self.assertRaisesRegex(ValueError, "Inf"):
            self.mask(d)
        self.assertTrue(np.isinf(d.loc[4, "ratio_lag_150m"]))

    def test_only_explained_history_nulls(self):
        d = self.data.copy()
        d.loc[4, "hour_sin"] = np.nan
        self.assertFalse(self.mask(d).partial.iloc[4])
        d = self.data.copy()
        d.loc[4, "ratio_diff_30m"] = np.nan
        self.assertFalse(self.mask(d).partial.iloc[4])

    def test_not_all_ineligible_rows_admitted(self):
        d = self.data.copy()
        d.loc[7, ["feature_valid", "classification_eligible"]] = False
        self.assertFalse(self.mask(d).partial.iloc[7])  # 과거 관측은 모두 존재
        d.loc[7, "feature_valid"] = True
        self.assertFalse(self.mask(d).partial.iloc[7])

    def test_unconfirmed_normalization_is_closed(self):
        m = self.mask(confirmed=False)
        self.assertFalse(m.partial.any())
        np.testing.assert_array_equal(m.baseline, self.data.classification_eligible)

    def test_outlier_history_not_clipped(self):
        d = self.data.copy()
        d.loc[0, "ratio_pct"] = -10.
        m = self.mask(d)
        self.assertTrue(m.partial.iloc[4])
        self.assertEqual(d.loc[0, "ratio_pct"], -10.)

    def test_batch_edges_and_full_preparation(self):
        data = pd.concat([fixture("2024-01-01"), fixture("2025-12-01"),
                          fixture("2026-07-01")], ignore_index=True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"input.parquet"
            data.to_parquet(path, index=False)
            prepared = prepare(path, "N3-C", normalized_silver_confirmed=True, batch_size=2)
            for name, split in prepared["datasets"].items():
                expected = int(data.classification_eligible.sum()/3)
                self.assertEqual(prepared["metadata"]["audit"][name]["baseline"], expected)
                self.assertTrue(split["rows"].history_cohort.eq("partial").any())
                self.assertTrue(split["X"].isna().any().any())
                self.assertTrue(split["X"].index.equals(split["y"].index))
                period = {"train": "2024-01-01", "validation": "2025-12-01", "test": "2026-07-01"}[name]
                original = fixture(period)
                expected_x = original.loc[original.classification_eligible, list(FEATURE_COLUMNS)].reset_index(drop=True)
                actual_x = split["X"].loc[split["rows"].history_cohort.eq("complete")].reset_index(drop=True)
                pd.testing.assert_frame_equal(actual_x, expected_x)

            self.assertEqual(prepared["metadata"]["training_source"], "tw_cems")
            self.assertIsNone(prepared["metadata"]["source_weights"])
            points = select_validation_points(
                prepared["datasets"]["validation"]["y"],
                np.where(prepared["datasets"]["validation"]["y"].eq(1), .8, .2))
            data_test = prepared["datasets"]["test"]
            metrics = evaluate_rows(data_test, np.where(data_test["y"].eq(1), .7, .1),
                                    points, len(fixture()))
            self.assertIn("partial", metrics)
            self.assertEqual(points["selection_split"], "tw_cems_validation")
            events = event_report(prepared["catalogs"]["test"], data_test["rows"],
                                  np.where(data_test["y"].eq(1), .9, .1), .5)
            self.assertGreater(events["all"]["observed_events"], 0)

    def test_fingerprint_and_time_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"one.parquet"
            p.write_bytes(b"one")
            before = fingerprint(local_files(p))
            p.write_bytes(b"two")
            self.assertNotEqual(before, fingerprint(local_files(p)))
        with self.assertRaises(ValueError):
            normalize_times(pd.Series(pd.to_datetime(["2024-01-01 00:01"])))

    def test_legacy_contract_still_rejects_bad_baseline(self):
        d = self.data.copy()
        d.loc[7, "ratio_lag_30m"] = np.nan
        with self.assertRaises(ValueError):
            self.mask(d)

    def test_single_fit_no_source_weights(self):
        class FakeClassifier:
            def __init__(self, **params):
                self.params = params
                self.calls = []
            def fit(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return self
        m = self.mask()
        d = self.data.loc[m.eligible_v2].reset_index(drop=True)
        split = {"X": d.loc[:, list(FEATURE_COLUMNS)], "y": d.label_entry_60m,
                 "rows": pd.DataFrame({"history_cohort": np.where(d.feature_valid, "complete", "partial")})}
        with patch("v2.train_entrypoint.version", return_value="3.4.1"),              patch.dict(sys.modules, {"xgboost": SimpleNamespace(XGBClassifier=FakeClassifier)}),              patch("v2.train_entrypoint._log_memory"):
            for model_id in SCALES:
                model = fit_candidate({n: split for n in ("train", "validation", "test")}, model_id)
                self.assertEqual(len(model.calls), 1)
                self.assertEqual(model.calls[0][1], {})
                self.assertEqual(model.params, {"random_state": 42,
                                              "scale_pos_weight": SCALES[model_id]})

    def test_warning_bundles_and_no_test_threshold_selection(self):
        t = pd.to_datetime(["2026-07-01 23:30", "2026-07-02 00:00",
                            "2026-07-02 01:00"]).tz_localize("Asia/Taipei")
        rows = pd.DataFrame({"stack_code": ["s"]*3, "item_code": ["nox"]*3,
                             "measured_at": t})
        r = warning_bundles(rows, [0, 0, 0], [.8, .8, .8], .5)
        self.assertEqual(r["false_bundles"], 2)
        self.assertEqual(r["false_bundles_by_day"]["2026-07-01"], 1)
        r = warning_bundles(rows, [1, 0, 0], [.8, .8, .8], .5)
        self.assertEqual(r["mixed_bundles"], 1)

    def test_embargo_and_outside_period(self):
        data = pd.concat([fixture("2025-10-31 18:00"), fixture("2025-12-01"),
                          fixture("2026-07-01")], ignore_index=True)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"input.parquet"
            data.to_parquet(p, index=False)
            result = prepare(p, "N3-C", normalized_silver_confirmed=True, batch_size=5)
            train_times = result["datasets"]["train"]["rows"].measured_at
            self.assertTrue(train_times.lt(pd.Timestamp("2025-10-31 23:00", tz="Asia/Taipei")).all())
            invalid = pd.concat([fixture("2023-10-01"), data], ignore_index=True)
            invalid.to_parquet(p, index=False)
            with self.assertRaisesRegex(ValueError, "확정 기간 밖"):
                prepare(p, "N3-C", normalized_silver_confirmed=True)

    def test_evaluate_and_atomic_artifacts(self):
        from v2.train_entrypoint import run
        from v2.artifacts import load_model
        import json
        data = pd.concat([fixture("2024-01-01"), fixture("2025-12-01"),
                          fixture("2026-07-01")], ignore_index=True)
        class PredictOnlyModel:
            classes_ = np.array([0, 1])
            def predict_proba(self, x):
                p = np.where(x.ratio_pct.ge(45), .8, .2)
                return np.column_stack([1-p, p])
            def get_params(self, deep=False):
                return {"random_state": 42, "scale_pos_weight": 1, "missing": np.nan}
            def get_booster(self):
                return SimpleNamespace(save_config=lambda: '{"test_double": true}')
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/"input.parquet"
            data.to_parquet(source, index=False)
            # 테스트 double은 직렬화 가능한 간단한 객체로만 저장한다. 실제 XGBoost fit 아님.
            from v2.artifacts import save_artifacts as real_save
            def save(model, model_id, metrics, metadata, parent):
                return real_save({"test_double": True}, model_id, metrics, metadata, parent)
            with patch("v2.train_entrypoint.fit_candidate", return_value=PredictOnlyModel()), \
                 patch("v2.train_entrypoint.version", return_value="3.4.1"), \
                 patch("v2.train_entrypoint.save_artifacts", side_effect=save), \
                 patch("v2.train_entrypoint._log_memory"):
                paths = run("N3-C", source, Path(folder)/"results", normalized_silver_confirmed=True)
            self.assertTrue(all(path.exists() for path in paths.values()))
            metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
            metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
            self.assertEqual(metadata["scale_pos_weight"], 1)
            self.assertEqual(metadata["validation_points"]["selection_split"], "tw_cems_validation")
            self.assertIn("partial_at_minus60", metrics["test"]["events"])
            self.assertEqual(load_model(paths["model"]), {"test_double": True})
            with self.assertRaises(FileExistsError):
                run("N3-C", source, Path(folder)/"results", normalized_silver_confirmed=True)

    def test_review_only_without_sdk_or_aws(self):
        from v2.sagemaker_job import main
        with patch.dict(sys.modules, {"boto3": None}), contextlib.redirect_stdout(io.StringIO()):
            settings = main(["--model-id", "N3-C",
                             "--input-s3-uri", "s3://test-input/cems/",
                             "--output-s3-uri", "s3://test-output/e-ml-training-v2-partial/",
                             "--role-arn", "arn:aws:iam::123456789012:role/test"])
        self.assertEqual(settings["mode"], "review_only")
        self.assertEqual(settings["instance_count"], 1)
        self.assertEqual(settings["scale_pos_weight"], 1)
        self.assertFalse(settings["domestic_final_data_access"])


if __name__ == "__main__":
    unittest.main()
