"""S3.1-C 신규 연결만 검증. AWS·실제 학습·기존 V2 테스트 재실행 없음."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2.test_partial_history import fixture
from v2.dataset import prepare as prepare_taiwan
from s31.config import MODEL_ID, OUTPUT_S3_ROOT, SNAPSHOTS
from s31.dataset import domestic_sql, domestic_batches, prepare_domestic, prepare_mixed
from s31.train_entrypoint import fit_classifier
from s31.sagemaker_job import main as review
from s31.artifacts import save_artifacts


def domestic(source):
    frame = fixture("2026-11-10 18:00").iloc[:12].copy()
    frame["item_code"] = "sox"
    frame["data_source"] = source
    return frame


class S31Tests(unittest.TestCase):
    def test_fixed_snapshot_sql_and_one_query_adapter(self):
        for source in SNAPSHOTS:
            query = domestic_sql(source)
            self.assertIn("FOR VERSION AS OF " + str(SNAPSHOTS[source]["snapshot_id"]), query)
            self.assertIn("2026-10-30 21:30:00", query)
            self.assertIn("measured_at < TIMESTAMP '2026-11-11 00:00:00'", query)
            self.assertIn("item_code = 'sox'", query)
            calls = []
            def read(**kwargs):
                calls.append(kwargs)
                return iter([domestic(source)])
            fake = SimpleNamespace(athena=SimpleNamespace(read_sql_query=read))
            with patch.dict(sys.modules, {"awswrangler": fake}):
                frames = list(domestic_batches(source, 2))
            self.assertEqual(len(calls), 1)
            self.assertFalse(calls[0]["ctas_approach"])
            self.assertFalse(calls[0]["unload_approach"])
            self.assertEqual(frames[0].attrs["snapshot_id"], SNAPSHOTS[source]["snapshot_id"])

    def test_domestic_nan_quality_and_train_embargo(self):
        frame = domestic("ktms")
        context = fixture("2026-10-30 22:00").iloc[:2].copy()
        context.item_code = "sox"
        context.data_source = "ktms"
        frame = pd.concat([context, frame], ignore_index=True)
        before = frame.copy(deep=True)
        split, audit = prepare_domestic(
            "ktms", [frame.iloc[:5], frame.iloc[5:]],
            normalized_silver_confirmed=True, batch_size=2)
        self.assertEqual(audit["snapshot_id"], 5489130650729135006)
        self.assertEqual(audit["context_rows"], 2)
        self.assertEqual(audit["embargo_rows"], 2)
        self.assertGreater(audit["partial_rows"], 0)
        self.assertTrue(split["X"].isna().any().any())
        self.assertEqual(str(split["rows"].measured_at.dt.tz), "Asia/Seoul")
        self.assertTrue(split["rows"].measured_at.ge(
            pd.Timestamp("2026-10-31", tz="Asia/Seoul")).all())
        self.assertTrue(split["rows"].measured_at.lt(
            pd.Timestamp("2026-11-10 23:00", tz="Asia/Seoul")).all())
        pd.testing.assert_frame_equal(frame, before)

    def test_mixed_data_no_weights_and_single_fit(self):
        data = pd.concat([fixture("2024-01-01"), fixture("2025-12-01"),
                          fixture("2026-07-01")], ignore_index=True)
        data.item_code = "sox"
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"tw.parquet"
            data.to_parquet(p, index=False)
            taiwan = prepare_taiwan(p, "S3-C", normalized_silver_confirmed=True)
        class FakeClassifier:
            def __init__(self, **kwargs):
                self.params, self.calls = kwargs, []
            def fit(self, *args, **kwargs):
                self.calls.append((args, kwargs))
        with patch("s31.dataset.prepare_taiwan", return_value=taiwan):
            prepared = prepare_mixed("not-read", normalized_silver_confirmed=True,
                supplied_domestic={source: iter([domestic(source)]) for source in SNAPSHOTS},
                batch_size=2)
        train = prepared["datasets"]["train"]
        self.assertNotIn("sample_weight", train)
        self.assertNotIn("source_weights", prepared["metadata"])
        self.assertEqual(set(train["rows"].data_source), {"tw_cems", "ktms", "ktms_synth"})
        self.assertEqual(prepared["metadata"]["model_id"], MODEL_ID)
        self.assertTrue(all(set(record) == {"data_source", "train_rows", "positive_ratio"}
                            for record in prepared["metadata"]["training_sources"]))
        self.assertEqual(sum(x["train_rows"] for x in prepared["metadata"]["training_sources"]),
                         len(train["y"]))
        self.assertEqual(str(train["rows"].measured_at.dt.tz), "UTC")
        self.assertTrue(train["rows"].measured_at.is_monotonic_increasing)
        with patch("s31.train_entrypoint.version", return_value="3.4.1"), \
             patch.dict(sys.modules, {"xgboost": SimpleNamespace(XGBClassifier=FakeClassifier)}), \
             patch("s31.train_entrypoint._log_memory"):
            model = fit_classifier(prepared["datasets"])
        self.assertEqual(model.params, {"random_state": 42, "scale_pos_weight": 5})
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(model.calls[0][1], {})
        self.assertEqual(len(model.calls[0][0]), 2)

    def test_artifact_namespace_no_old_module_changes(self):
        import artifacts as original
        import v2.artifacts as previous
        before, v2before = original.MODEL_IDS, previous._shared.MODEL_IDS
        with tempfile.TemporaryDirectory() as folder:
            paths = save_artifacts({"test": True}, {}, {"model_id": MODEL_ID}, folder)
            self.assertEqual(paths["model"].parent, Path(folder)/MODEL_ID)
            self.assertEqual({p.name for p in paths["model"].parent.iterdir()},
                             {"model.joblib", "metrics.json", "metadata.json"})
            with self.assertRaises(FileExistsError):
                save_artifacts({}, {}, {}, folder)
        self.assertEqual(original.MODEL_IDS, before)
        self.assertEqual(previous._shared.MODEL_IDS, v2before)

    def test_review_only_no_aws_and_unique_prefix(self):
        with patch.dict(sys.modules, {"boto3": None, "awswrangler": None}), \
             contextlib.redirect_stdout(io.StringIO()):
            settings = review(["--role-arn", "arn:aws:iam::952900391026:role/test"])
        self.assertEqual(settings["mode"], "review_only")
        self.assertEqual(settings["model_id"], "S3.1-C")
        self.assertEqual(settings["scale_pos_weight"], 5)
        self.assertFalse(settings["fit_uses_sample_weight"])
        self.assertTrue(settings["output_s3_uri"].startswith(OUTPUT_S3_ROOT))
        self.assertEqual(settings["output_s3_uri"].count("/S3.1-C/"), 1)
        self.assertFalse(settings["domestic_evaluation_access"])
        self.assertNotIn(".", settings["job_name"])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                review(["--role-arn", "arn:aws:iam::952900391026:role/test",
                        "--output-s3-uri", "s3://smokestack-tms-raw-952900391026/wrong"])


if __name__ == "__main__":
    unittest.main()
