"""학습·AWS 호출 없이 수행하는 날짜·무결성·배치 정합성 최소 로컬 검사."""

import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal

import dataset as pipeline
from contract import NUMERIC_COLUMNS, REQUIRED_COLUMNS, validate_contract
from features import FEATURE_COLUMNS
from split import split_by_time


class PipelineCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ml-pipeline-check-")
        self.root = Path(self.temporary.name).resolve()
        self.root.relative_to(Path(tempfile.gettempdir()).resolve())

    def tearDown(self):
        self.temporary.cleanup()
        self.assertFalse(self.root.exists())

    def test_syntax_and_imports_without_running_main(self):
        names = (
            "contract", "features", "split", "dataset", "train_n1", "train_s1",
            "train_rf", "evaluation", "artifacts", "train_entrypoint", "sagemaker_job",
        )
        for name in names:
            with self.subTest(module=name):
                path = Path(__file__).parent / f"{name}.py"
                compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")
                importlib.import_module(name)

    def test_missing_edge_slots_and_fixed_boundaries(self):
        frame = pd.DataFrame({"measured_at": pd.to_datetime([
            "2023-11-02 00:30", "2025-11-01 00:00", "2026-10-30 23:30",
        ])})
        splits, metadata = split_by_time(frame)
        self.assertEqual({name: len(value) for name, value in splits.items()},
                         {"train": 1, "validation": 1, "test": 1})
        self.assertEqual(str(metadata["validation_start"]), "2025-11-01 00:00:00+08:00")
        self.assertEqual(str(metadata["test_start"]), "2026-05-01 00:00:00+08:00")

    def test_leakage_boundaries_and_out_of_range_errors(self):
        frame = pd.DataFrame({"measured_at": pd.to_datetime([
            "2023-11-01 00:00", "2025-10-31 22:30", "2025-10-31 23:00",
            "2025-10-31 23:30", "2025-11-01 00:00", "2026-04-30 22:30",
            "2026-04-30 23:00", "2026-04-30 23:30", "2026-05-01 00:00",
            "2026-10-31 23:30",
        ])})
        splits, metadata = split_by_time(frame)
        self.assertEqual(splits["train"].index.tolist(), [0, 1])
        self.assertEqual(splits["validation"].index.tolist(), [4, 5])
        self.assertEqual(splits["test"].index.tolist(), [8, 9])
        self.assertEqual(metadata["excluded_rows"], 4)
        for outside in ("2023-10-31 23:30", "2026-11-01 00:00"):
            with self.subTest(outside=outside), self.assertRaisesRegex(ValueError, "확정 기간"):
                split_by_time(pd.DataFrame({"measured_at": pd.to_datetime([outside])}))

    def test_checksums_without_file_size_or_mtime_change(self):
        path = self.root / "checksum.bin"
        path.write_bytes(b"original-input")
        baseline = pipeline._file_fingerprint(str(path))
        timestamps = path.stat()
        path.write_bytes(b"modified-input")
        os.utime(path, ns=(timestamps.st_atime_ns, timestamps.st_mtime_ns))
        changed = pipeline._file_fingerprint(str(path))
        self.assertEqual(baseline[3], changed[3])  # 파일 크기는 동일하다.
        self.assertEqual(baseline[4], changed[4])  # 수정 시각도 복원했다.
        self.assertNotEqual(baseline[-1], changed[-1])
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            pipeline._check_snapshot((changed,), (baseline,))

    def _frame(self):
        times = pd.to_datetime([
            "2026-10-30 23:30", "2023-11-02 00:30", "2025-10-31 22:30",
            "2025-10-31 23:00", "2025-10-31 23:30", "2025-11-01 00:00",
            "2025-11-01 00:00", "2026-04-30 22:30", "2026-04-30 23:00",
            "2026-05-01 00:00", "2026-05-01 00:30", "2024-02-01 00:00",
            "2025-12-01 00:00",
        ])
        count = len(times)
        frame = pd.DataFrame({
            name: [float(position) for position in range(count)] for name in NUMERIC_COLUMNS
        })
        frame["stack_code"] = "test-stack"
        frame["item_code"] = ["sox" if i in (1, 4, 7, 10) else "nox" for i in range(count)]
        frame["measured_at"] = times
        frame["feature_valid"] = [i != 11 for i in range(count)]
        frame["classification_eligible"] = [i != 12 for i in range(count)]
        frame["regression_eligible"] = [i != 6 for i in range(count)]
        frame["feature_version"] = "v1"
        frame["label_version"] = "v1"
        frame["quality_policy_version"] = "v2"
        frame["label_entry_60m"] = [i % 2 for i in range(count)]
        frame.loc[0, "label_ratio_60m"] = 150.0
        frame.loc[2, "label_ratio_60m"] = -3.0
        frame.loc[2, "ratio_pct"] = -5.0
        frame.loc[5, "ratio_lag_150m"] = float("nan")
        frame.index = pd.Index([7] * count, name="source_row")
        return frame.loc[:, list(REQUIRED_COLUMNS)]

    def test_parquet_batches_match_reference_rows_features_and_labels(self):
        import pyarrow.dataset as ds

        frame = self._frame()
        original = frame.copy(deep=True)
        inputs = self.root / "parquet"
        inputs.mkdir()
        frame.iloc[:6].to_parquet(inputs / "part-0.parquet", index=True, row_group_size=2)
        frame.iloc[6:].to_parquet(inputs / "part-1.parquet", index=True, row_group_size=2)
        original_dataset = ds.dataset
        scans = []

        class SmallBatches:
            def __init__(self, source):
                self.source = source

            def __getattr__(self, name):
                return getattr(self.source, name)

            def scanner(self, **kwargs):
                scans.append(tuple(kwargs["columns"]))
                kwargs["batch_size"] = 2
                return self.source.scanner(**kwargs)

        def wrapped_dataset(*args, **kwargs):
            return SmallBatches(original_dataset(*args, **kwargs))

        times = frame["measured_at"].dt.tz_localize("Asia/Taipei")
        date = lambda value: pd.Timestamp(value, tz="Asia/Taipei")
        masks = {
            "train": (times >= date("2023-11-01")) & (times < date("2025-10-31 23:00")),
            "validation": (times >= date("2025-11-01")) & (times < date("2026-04-30 23:00")),
            "test": (times >= date("2026-05-01")) & (times < date("2026-11-01")),
        }
        for task in ("classification", "regression"):
            for pollutant in ("nox", "sox"):
                with self.subTest(task=task, pollutant=pollutant):
                    scans.clear()
                    with patch.object(ds, "dataset", side_effect=wrapped_dataset):
                        prepared, metadata = pipeline.prepare_datasets(inputs, task, pollutant)
                    self.assertEqual(len(scans), 2)
                    self.assertTrue(set(REQUIRED_COLUMNS).issubset(scans[0]))
                    self.assertNotIn("measure_value", scans[1])
                    self.assertNotIn("standard_value", scans[1])
                    label = "label_entry_60m" if task == "classification" else "label_ratio_60m"
                    eligible = (frame["item_code"].eq(pollutant) & frame["feature_valid"]
                                & frame[f"{task}_eligible"])
                    for name, mask in masks.items():
                        expected = frame.loc[mask & eligible].sort_values("measured_at", kind="stable")
                        assert_frame_equal(prepared[name]["X"], expected.loc[:, list(FEATURE_COLUMNS)])
                        assert_series_equal(prepared[name]["y"], expected[label])
                        self.assertEqual(metadata["prepared_rows"][name], len(expected))
                        self.assertEqual(metadata["has_valid_data"][name], not expected.empty)
                    self.assertEqual(metadata["excluded_rows"], 3)
        assert_frame_equal(frame, original)

    def test_parquet_content_and_file_list_changes_are_rejected(self):
        frame = self._frame()
        for change in ("content", "addition", "deletion"):
            with self.subTest(change=change):
                directory = self.root / change
                directory.mkdir()
                path = directory / "part.parquet"
                frame.to_parquet(path, index=True)
                with self.assertRaises(ValueError):
                    with pipeline._parquet_snapshot(directory) as (_, check):
                        if change == "content":
                            with path.open("r+b") as stream:
                                stream.seek(8)
                                byte = stream.read(1)
                                stream.seek(8)
                                stream.write(bytes([byte[0] ^ 1]))
                        elif change == "addition":
                            frame.to_parquet(directory / "added.parquet", index=True)
                        else:
                            path.unlink()
                        check()

    def test_empty_eligible_period_and_version_errors(self):
        frame = self._frame()
        frame["classification_eligible"] = False
        prepared, metadata = pipeline.prepare_datasets(frame, "classification", "nox")
        self.assertEqual(metadata["has_valid_data"], {"train": False, "validation": False, "test": False})
        self.assertTrue(all(value["X"].empty and value["y"].empty for value in prepared.values()))
        for column in ("feature_version", "label_version", "quality_policy_version"):
            with self.subTest(column=column):
                changed = frame.copy()
                changed[column] = "invalid-version"
                with self.assertRaisesRegex(ValueError, column):
                    validate_contract(changed)


if __name__ == "__main__":
    unittest.main()
