"""공용 fixture. 로컬 SparkSession(Java 17 필요)과 가짜 데이터 폴더."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyspark.sql import SparkSession

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def spark():
    session = (
        SparkSession.builder.master("local[2]")
        .appName("tms-eda-tests")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR
