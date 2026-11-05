"""tw_cems_parquet 변환 테스트.

tests/fixtures/*.jsonl은 모두 **가짜 데이터**다. 실제 TW CEMS 원본에서 가져온 값이 아니며,
키 이름과 형식만 2024-03 원본을 흉내 냈다. 출력은 pytest의 tmp_path에만 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyspark.sql.types import StringType

import tw_cems_parquet as twp

EDGE = "synthetic_edge_cases.jsonl"
MONTH_B = "synthetic_month_b.jsonl"
CASE_CONFLICT = "synthetic_case_conflict.jsonl"

EDGE_NON_EMPTY_LINES = 8  # 손상 줄 1개 포함, 빈 줄 1개 제외


def _input_keys(path: Path) -> set[str]:
    """JSON으로 읽히는 줄의 키 합집합 (손상 줄·빈 줄 제외)."""
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            keys.update(json.loads(line))
        except json.JSONDecodeError:
            continue
    return keys


def _convert(spark, fixtures_dir: Path, name: str, out_root: Path, year: str, month: str):
    args = twp.parse_args(
        [
            "--local",
            "--year",
            year,
            "--month",
            month,
            "--input_path",
            str(fixtures_dir / name),
            "--output_path",
            str(out_root),
        ]
    )
    input_path, output_path = twp.resolve_paths(args)
    summary = twp.convert(spark, input_path, output_path)
    return summary, Path(output_path)


@pytest.fixture
def edge_output(spark, fixtures_dir, tmp_path):
    summary, out_dir = _convert(spark, fixtures_dir, EDGE, tmp_path, "2025", "03")
    return summary, out_dir, spark.read.parquet(str(out_dir))


# ---------------------------------------------------------------------------
# 행 수·손상 줄
# ---------------------------------------------------------------------------


def test_fixture_line_count_constant_matches_file(fixtures_dir):
    lines = (fixtures_dir / EDGE).read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if line.strip()) == EDGE_NON_EMPTY_LINES


def test_row_count_equals_non_empty_input_lines(edge_output):
    _summary, _out_dir, df = edge_output
    assert df.count() == EDGE_NON_EMPTY_LINES


def test_corrupt_line_is_kept_as_one_row(edge_output):
    _summary, _out_dir, df = edge_output
    corrupt = df.filter(df[twp.CORRUPT_COLUMN].isNotNull()).collect()
    assert len(corrupt) == 1
    assert corrupt[0][twp.CORRUPT_COLUMN].startswith('{"cno": "F0009"')


# ---------------------------------------------------------------------------
# 키·값 보존
# ---------------------------------------------------------------------------


def test_all_input_keys_are_output_columns(fixtures_dir, edge_output):
    summary, _out_dir, df = edge_output
    assert _input_keys(fixtures_dir / EDGE) <= set(df.columns)
    assert {"flareno", "locationno", "polno"} <= set(df.columns)
    assert twp.SOURCE_FILE_COLUMN in df.columns
    assert set(summary["columns"]) == set(df.columns)
    assert summary["column_count"] == len(df.columns)


def test_source_file_points_to_input_file(edge_output):
    _summary, _out_dir, df = edge_output
    values = {r[0] for r in df.select(twp.SOURCE_FILE_COLUMN).distinct().collect()}
    assert len(values) == 1
    assert values.pop().endswith(f"fixtures/{EDGE}")


def test_values_are_kept_as_original_strings(edge_output):
    _summary, _out_dir, df = edge_output
    rows = {r["_id"]: r for r in df.filter(df["_id"].isNotNull()).collect()}

    assert rows["3"]["std"] == "nan"
    assert rows["3"]["m_value"] == ""
    assert rows["3"]["std_s"] == ""
    assert rows["2"]["m_value"] == "12.30"  # 숫자 리터럴도 원문 문자열
    assert rows["2"]["m_time"] == "2025/3/1 0:30"
    assert rows["3"]["m_time"] == "2025-03-01T00:45:00"
    assert rows["4"]["polno"] is None  # 그 줄에 없는 키는 NULL


def test_all_columns_are_strings(edge_output):
    _summary, _out_dir, df = edge_output
    not_string = [f.name for f in df.schema.fields if not isinstance(f.dataType, StringType)]
    assert not_string == []


def test_duplicate_rows_are_kept(edge_output):
    _summary, _out_dir, df = edge_output
    assert df.filter(df["_id"] == "5").count() == 2


# ---------------------------------------------------------------------------
# 출력 폴더
# ---------------------------------------------------------------------------


def test_output_has_success_marker_and_at_most_two_parts(edge_output):
    _summary, out_dir, _df = edge_output
    assert (out_dir / "_SUCCESS").exists()
    parts = list(out_dir.glob("part-*.parquet"))
    assert 1 <= len(parts) <= twp.OUTPUT_FILES_PER_MONTH


def test_two_months_keep_own_keys_and_union(spark, fixtures_dir, tmp_path):
    _s1, march = _convert(spark, fixtures_dir, EDGE, tmp_path, "2025", "03")
    _s2, april = _convert(spark, fixtures_dir, MONTH_B, tmp_path, "2025", "04")

    df_march = spark.read.parquet(str(march))
    df_april = spark.read.parquet(str(april))
    assert "extra_note" in df_april.columns and "extra_note" not in df_march.columns
    assert "std_s" in df_march.columns and "std_s" not in df_april.columns

    merged = df_march.unionByName(df_april, allowMissingColumns=True)
    assert merged.count() == EDGE_NON_EMPTY_LINES + 2


def test_rerun_overwrites_only_that_month(spark, fixtures_dir, tmp_path):
    _convert(spark, fixtures_dir, MONTH_B, tmp_path, "2025", "04")
    _convert(spark, fixtures_dir, EDGE, tmp_path, "2025", "03")
    _s, march = _convert(spark, fixtures_dir, EDGE, tmp_path, "2025", "03")

    assert spark.read.parquet(str(march)).count() == EDGE_NON_EMPTY_LINES
    april = tmp_path / "year=2025" / "month=04"
    assert (april / "_SUCCESS").exists()
    assert spark.read.parquet(str(april)).count() == 2


def test_case_conflict_fails_without_output(spark, fixtures_dir, tmp_path):
    with pytest.raises(ValueError, match="ImportDate"):
        _convert(spark, fixtures_dir, CASE_CONFLICT, tmp_path, "2025", "05")
    assert not (tmp_path / "year=2025" / "month=05").exists()


def test_missing_input_file_raises(spark, tmp_path):
    with pytest.raises(Exception, match="(?i)path does not exist|PATH_NOT_FOUND"):
        twp.convert(spark, str(tmp_path / "nope.jsonl"), str(tmp_path / "out"))
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# 인자
# ---------------------------------------------------------------------------


def test_parse_args_ignores_glue_arguments():
    args = twp.parse_args(
        ["--JOB_NAME", "x", "--TempDir", "s3://b/glue-temp/", "--year", "2025", "--month", "03"]
    )
    assert (args.year, args.month, args.local) == ("2025", "03", False)


@pytest.mark.parametrize("month", ["3", "13", "00"])
def test_parse_args_rejects_bad_month(month):
    with pytest.raises(SystemExit):
        twp.parse_args(["--year", "2025", "--month", month])


def test_parse_args_rejects_bad_year():
    with pytest.raises(SystemExit):
        twp.parse_args(["--year", "25", "--month", "03"])


def test_parse_args_local_requires_paths():
    with pytest.raises(SystemExit):
        twp.parse_args(["--local", "--year", "2025", "--month", "03", "--input_path", "a"])


def test_resolve_paths_builds_partition_paths():
    args = twp.parse_args(["--year", "2025", "--month", "03", "--eda_bucket", "eda"])
    input_path, output_path = twp.resolve_paths(args)
    assert input_path == (
        "s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/2025-03.jsonl"
    )
    assert output_path == "s3://eda/tw_cems_raw/year=2025/month=03/"


def test_resolve_paths_local():
    args = twp.parse_args(
        ["--local", "--year", "2025", "--month", "03", "--input_path", "in.jsonl"]
        + ["--output_path", "/tmp/out/"]
    )
    assert twp.resolve_paths(args) == ("in.jsonl", "/tmp/out/year=2025/month=03/")
