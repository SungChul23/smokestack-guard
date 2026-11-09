"""glue_tw_cems_silver 테스트. 로컬 Spark로 실행하며 fixture는 모두 가짜 데이터다."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import glue_tw_cems_silver as g

COLUMNS = [
    "area_nm", "fact_manage_nm", "stack_code", "item", "unit", "value", "limit", "status",
    "ts_kst", "ratio", "ts_local", "code2", "flag_code_ratio_mismatch",
]  # fmt: skip
SORT = ["stack_code", "item", "unit", "ts_kst"]
STATUSES = {"ok", "not_monitored", "other_code", "partial", "invalid"}


def _run(spark, src: Path, out: Path, runs: Path, year: str, month: str) -> dict:
    return g.main(
        [
            "--local",
            "--year", year,
            "--month", month,
            "--input_path", str(src),
            "--output_path", str(out),
            "--runs_path", str(runs),
            "--JOB_NAME", "ignored-glue-arg",
        ]
    )  # fmt: skip


def _files(part: Path) -> list[str]:
    return sorted(p.name for p in part.glob("*.parquet"))


def _rows(spark, path: Path, year: str, month: str):
    df = spark.read.parquet(str(path)).where(f"year = '{year}' and month = '{month}'")
    return df


@pytest.fixture()
def dirs(tmp_path):
    return tmp_path / "silver" / "tw_cems", tmp_path / "runs"


# ---------------------------------------------------------------------------
# 1. 정상 달
# ---------------------------------------------------------------------------


def test_normal_month_writes_one_partition_and_run_record(spark, fixtures_dir, dirs):
    out, runs = dirs
    record = _run(spark, fixtures_dir / "synthetic_2025_10.jsonl", out, runs, "2025", "10")

    assert sorted(p.name for p in out.glob("year=*")) == ["year=2025"]
    assert sorted(p.name for p in (out / "year=2025").glob("month=*")) == ["month=10"]
    assert len(_files(out / "year=2025" / "month=10")) == 1  # 작은 파일 방지: 한 달 = 파일 1개

    saved = json.loads((runs / "2025-10.json").read_text(encoding="utf-8"))
    assert saved == record
    assert saved["month"] == "2025-10"
    assert saved["input_rows"] == 9
    assert set(saved["status_rows"]) == STATUSES
    assert all(n >= 1 for n in saved["status_rows"].values())
    assert saved["silver_rows"] == sum(saved["status_rows"].values())
    assert saved["silver_rows"] == _rows(spark, out, "2025", "10").count()
    for key in ("spark", "python", "pandas", "numpy"):
        assert saved["versions"][key]
    assert saved["package_md5"] == "unknown"
    assert saved["job_run_id"] == "local"


# ---------------------------------------------------------------------------
# 2. 다른 달 행이 섞이면 쓰기 전에 실패
# ---------------------------------------------------------------------------


def test_mixed_month_fails_before_write_and_keeps_other_month(spark, fixtures_dir, dirs):
    out, runs = dirs
    _run(spark, fixtures_dir / "synthetic_2025_09.jsonl", out, runs, "2025", "09")
    sep = out / "year=2025" / "month=09"
    sep_files = _files(sep)
    sep_rows = _rows(spark, out, "2025", "09").count()

    with pytest.raises(ValueError) as exc:
        _run(spark, fixtures_dir / "synthetic_2025_10_mixed.jsonl", out, runs, "2025", "10")

    message = str(exc.value)
    assert "month mismatch" in message
    assert "expected 2025-10" in message
    assert '"2025-09": 1' in message
    assert _files(sep) == sep_files
    assert _rows(spark, out, "2025", "09").count() == sep_rows
    assert not (out / "year=2025" / "month=10").exists()
    assert not (runs / "2025-10.json").exists()


# ---------------------------------------------------------------------------
# 3. 결과 0행이면 실패
# ---------------------------------------------------------------------------


def test_empty_result_fails_and_writes_nothing(spark, tmp_path, dirs):
    out, runs = dirs
    src = tmp_path / "empty.jsonl"
    src.write_text(
        "\n".join(
            json.dumps({"cno": None, "polno": "P01", "m_time": "2025-10-01T00:00:00"})
            for _ in range(3)
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="empty silver for 2025-10"):
        _run(spark, src, out, runs, "2025", "10")

    assert not out.exists() or not any(out.rglob("*.parquet"))
    assert not (runs / "2025-10.json").exists()


# ---------------------------------------------------------------------------
# 4. 다시 실행하면 그 달만 교체
# ---------------------------------------------------------------------------


def test_rerun_replaces_only_that_month(spark, fixtures_dir, dirs):
    out, runs = dirs
    _run(spark, fixtures_dir / "synthetic_2025_09.jsonl", out, runs, "2025", "09")
    first = _run(spark, fixtures_dir / "synthetic_2025_10.jsonl", out, runs, "2025", "10")
    sep_files = _files(out / "year=2025" / "month=09")

    second = _run(spark, fixtures_dir / "synthetic_2025_10.jsonl", out, runs, "2025", "10")

    assert second["silver_rows"] == first["silver_rows"]
    assert second["status_rows"] == first["status_rows"]
    assert _rows(spark, out, "2025", "10").count() == first["silver_rows"]
    assert _files(out / "year=2025" / "month=09") == sep_files


# ---------------------------------------------------------------------------
# 5. 파티션 식과 결과가 C의 build()와 같다 (research R4)
# ---------------------------------------------------------------------------


def test_result_matches_tw_cems_spark_build(spark, fixtures_dir, tmp_path, dirs):
    from smokestack_guard.silver import tw_cems_spark

    out, runs = dirs
    src = fixtures_dir / "synthetic_2025_10.jsonl"
    out_c = tmp_path / "build_c"
    tw_cems_spark.build(spark, str(src), str(out_c))
    _run(spark, src, out, runs, "2025", "10")

    ours = spark.read.parquet(str(out))
    theirs = spark.read.parquet(str(out_c))

    def parts(df):
        return {(r.year, r.month) for r in df.select("year", "month").distinct().collect()}

    # 읽을 때 Spark가 파티션 값을 정수로 추론한다(2025, 10). 양쪽이 같은 값인지만 본다.
    assert parts(ours) == parts(theirs)
    assert len(parts(ours)) == 1
    assert ours.orderBy(*SORT).select(*COLUMNS).collect() == theirs.orderBy(*SORT).select(
        *COLUMNS
    ).collect()


# ---------------------------------------------------------------------------
# 6. 로그에 데이터 값이 없다
# ---------------------------------------------------------------------------


def test_log_has_no_data_values(spark, fixtures_dir, dirs, capsys):
    out, runs = dirs
    _run(spark, fixtures_dir / "synthetic_2025_10.jsonl", out, runs, "2025", "10")

    printed = capsys.readouterr().out
    assert printed.strip()
    for value in ("가짜사업장", "가짜시", "X001", "12.00", "9.20"):
        assert value not in printed


# ---------------------------------------------------------------------------
# 인자·순수 함수
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("month", ["13", "00", "1", "ab"])
def test_bad_month_is_rejected(month):
    with pytest.raises(SystemExit):
        g.parse_args(["--year", "2025", "--month", month])


def test_files_per_month_must_be_positive():
    with pytest.raises(SystemExit):
        g.parse_args(["--year", "2025", "--month", "10", "--files_per_month", "0"])


def test_local_requires_paths():
    with pytest.raises(SystemExit):
        g.parse_args(["--local", "--year", "2025", "--month", "10"])


def test_check_months_passes_only_expected_month():
    g.check_months({("2025", "10"): {"ok": 3}}, "2025", "10")
    with pytest.raises(ValueError, match="empty silver for 2025-10"):
        g.check_months({}, "2025", "10")
    with pytest.raises(ValueError, match="month mismatch"):
        g.check_months({("2025", "10"): {"ok": 1}, ("2025", "11"): {"ok": 2}}, "2025", "10")


def test_glue_paths_follow_contract():
    args = g.parse_args(
        ["--year", "2025", "--month", "10", "--raw_bucket", "raw", "--silver_bucket", "raw"]
    )
    paths = g.resolve_paths(args)
    assert paths.source == "s3://raw/bronze/tw_cems/historical/2025-10.jsonl"
    assert paths.output == "s3://raw/silver/tw_cems/"
    assert paths.partition == "s3://raw/silver/tw_cems/year=2025/month=10/"
    assert paths.run_record_key == "silver/_runs/tw_cems/2025-10.json"
