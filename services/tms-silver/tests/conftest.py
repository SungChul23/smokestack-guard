"""공용 fixture. 로컬 SparkSession(Spark 3.5.4, Java 17)과 가짜 데이터 폴더."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def spark():
    import os
    import sys
    import time

    from pyspark.sql import SparkSession

    # Python UDF·createDataFrame 작업자가 시스템 python이 아니라 같은 인터프리터를 쓰게 한다.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    # PySpark는 naive datetime을 프로세스 로컬 시간대로 해석한다.
    # Glue·CI처럼 UTC로 고정한다(로컬 PC는 KST).
    os.environ["TZ"] = "UTC"
    time.tzset()

    session = (
        SparkSession.builder.master("local[2]")
        .appName("tms-silver-tests")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.extraJavaOptions", "-Duser.timezone=UTC")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


# ---------------------------------------------------------------------------
# ML-ready (005): 가짜 Silver를 pandas와 Spark 양쪽으로
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def ml_ready_silver_pdf():
    from ml_ready_cases import build_silver

    return build_silver()


def silver_to_spark(spark, pdf):
    """pandas를 거치지 않고(createDataFrame(pandas) 미사용) 같은 값의 Spark DataFrame을 만든다."""
    from ml_ready_cases import SILVER_COLUMNS
    from pyspark.sql import types as T

    types = {
        "value": T.DoubleType(), "limit": T.DoubleType(), "ratio": T.DoubleType(),
        "ts_kst": T.TimestampType(), "ts_local": T.TimestampType(),
        "flag_code_ratio_mismatch": T.BooleanType(),
    }  # fmt: skip
    schema = T.StructType([T.StructField(c, types.get(c, T.StringType())) for c in SILVER_COLUMNS])
    def plain(v):
        if hasattr(v, "to_pydatetime"):
            return v.to_pydatetime()
        return v.item() if hasattr(v, "item") else v  # numpy 스칼라 → 파이썬 값

    rows = [
        tuple(plain(v) for v in row)
        for row in pdf[SILVER_COLUMNS].itertuples(index=False, name=None)
    ]
    return spark.createDataFrame(rows, schema)


@pytest.fixture(scope="session")
def ml_ready_silver_df(spark, ml_ready_silver_pdf):
    return silver_to_spark(spark, ml_ready_silver_pdf)
