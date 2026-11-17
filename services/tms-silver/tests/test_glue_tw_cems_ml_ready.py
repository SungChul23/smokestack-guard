"""glue_tw_cems_ml_ready 테스트. 로컬 Spark, 가짜 Silver(tests/ml_ready_cases.py)."""

from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest
from conftest import silver_to_spark
from ml_ready_cases import build_silver
from pyspark.sql import functions as F
from smokestack_guard.silver import ml_ready

import glue_tw_cems_ml_ready as g

BUILD_FIELDS = {
    "run_ts", "job_run_id", "mode", "source", "output", "silver_months", "silver_rows",
    "selected_rows", "duplicate_keys", "output_rows", "feature_valid_rows",
    "classification_eligible_rows", "regression_eligible_rows", "positive_rows",
    "eligible_positive_rows", "by_item", "files", "package_md5", "versions", "started_at",
    "finished_at",
}  # fmt: skip


@pytest.fixture()
def silver_dir(spark, ml_ready_silver_df, tmp_path):
    path = tmp_path / "silver" / "tw_cems"
    ml_ready_silver_df.withColumn("year", F.date_format("ts_local", "yyyy")).withColumn(
        "month", F.date_format("ts_local", "MM")
    ).write.partitionBy("year", "month").parquet(str(path))
    return path


def _build(src, out, runs, files=3):
    return g.main(
        [
            "--local", "--mode", "build", "--files", str(files),
            "--source_path", str(src), "--output_path", str(out), "--runs_path", str(runs),
            "--JOB_NAME", "ignored",
        ]
    )  # fmt: skip


def _parts(out):
    return sorted(out.glob("part-*.parquet"))


# ---------------------------------------------------------------------------
# 1. build 정상
# ---------------------------------------------------------------------------


def test_build_writes_sorted_time_ranges_and_records(silver_dir, tmp_path):
    out, runs = tmp_path / "ml_ready", tmp_path / "runs"
    record = _build(silver_dir, out, runs, files=3)

    parts = _parts(out)
    assert len(parts) == 3
    ranges = []
    for p in parts:
        ts = pq.read_table(p, columns=["measured_at"]).column("measured_at").to_pylist()
        assert ts == sorted(ts)  # 파일 안 정렬
        ranges.append((ts[0], ts[-1]))
    ranges.sort()
    for (_, end), (start, _) in zip(ranges, ranges[1:], strict=False):
        assert end <= start  # 파일 간 시간 구간이 겹치지 않음

    latest = json.loads((runs / "latest.json").read_text(encoding="utf-8"))
    by_run = json.loads((runs / "runs" / f"{record['run_ts']}.json").read_text(encoding="utf-8"))
    assert latest == by_run
    assert BUILD_FIELDS <= set(latest)
    assert latest["silver_months"] == ["2023-11", "2023-12", "2025-03", "2025-05", "2025-07",
                                       "2025-08", "2025-09", "2025-10"]  # fmt: skip
    assert latest["silver_rows"] == len(build_silver())
    assert latest["duplicate_keys"] == 0
    assert latest["output_rows"] == len(ml_ready.to_ml_ready(build_silver()))
    assert set(latest["by_item"]) == {"nox", "sox"}


# ---------------------------------------------------------------------------
# 2. 실패하면 latest.json이 없다
# ---------------------------------------------------------------------------


def test_failed_build_removes_latest(spark, silver_dir, tmp_path):
    out, runs = tmp_path / "ml_ready", tmp_path / "runs"
    _build(silver_dir, out, runs)
    assert (runs / "latest.json").exists()

    bad = build_silver().assign(status="invalid")
    bad_dir = tmp_path / "bad"
    silver_to_spark(spark, bad).write.parquet(str(bad_dir))
    with pytest.raises(ValueError, match="no ml-ready target rows"):
        _build(bad_dir, out, runs)
    assert not (runs / "latest.json").exists()


# ---------------------------------------------------------------------------
# 3. 다시 build
# ---------------------------------------------------------------------------


def test_rebuild_is_identical(silver_dir, tmp_path):
    out, runs = tmp_path / "ml_ready", tmp_path / "runs"
    first = _build(silver_dir, out, runs)
    second = _build(silver_dir, out, runs)
    keys = [k for k in BUILD_FIELDS if k.endswith("_rows") or k in ("duplicate_keys", "by_item")]
    assert {k: first[k] for k in keys} == {k: second[k] for k in keys}
    assert len(_parts(out)) == 3


# ---------------------------------------------------------------------------
# 4. compare (pandas가 쓴 정답지, 타임스탬프 ns)
# ---------------------------------------------------------------------------


def test_compare_with_pandas_reference(silver_dir, tmp_path):
    out, runs = tmp_path / "ml_ready", tmp_path / "runs"
    _build(silver_dir, out, runs)
    ref = tmp_path / "ref.parquet"
    ml_ready.to_ml_ready(build_silver()).to_parquet(ref, index=False)

    record = g.main(
        [
            "--local", "--mode", "compare",
            "--source_path", str(silver_dir), "--output_path", str(out),
            "--runs_path", str(runs), "--reference_path", str(ref),
        ]
    )  # fmt: skip
    assert record["passed"] is True
    saved = json.loads((runs / "compare" / f"{record['run_ts']}.json").read_text("utf-8"))
    assert saved["passed"] is True
    assert saved["theirs_measured_at_type"] == "bigint"  # ns로 저장된 것을 정수로 읽음


# ---------------------------------------------------------------------------
# 5. 로그에 값이 없다 / 인자
# ---------------------------------------------------------------------------


def test_log_has_no_values(silver_dir, tmp_path, capsys):
    _build(silver_dir, tmp_path / "ml_ready", tmp_path / "runs")
    printed = capsys.readouterr().out
    assert printed.strip()
    for value in ("0.7021", "70.21", "가짜사업장", "F001-P01"):
        assert value not in printed


@pytest.mark.parametrize("files", ["0", "33", "x"])
def test_files_out_of_range(files):
    with pytest.raises(SystemExit):
        g.parse_args(["--files", files])


def test_glue_paths_follow_contract():
    paths = g.resolve(g.parse_args(["--bucket", "raw"]))
    assert paths["source"] == "s3://raw/silver/tw_cems/"
    assert paths["output"] == "s3://raw/silver/tw_cems_ml_ready/"
    assert paths["reference"].endswith("/ml_ready/part.parquet")
