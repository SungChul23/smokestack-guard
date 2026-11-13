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


# ---------------------------------------------------------------------------
# K-TMS (008): 가짜 S3와 로컬 Iceberg
# ---------------------------------------------------------------------------


class FakeS3:
    """메모리 dict 기반 가짜 S3. C의 read_bronze와 실행 기록 쓰기가 쓰는 메서드만 있다."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body=b"", ContentType=None):  # noqa: N803 (boto3 인자 이름)
        self.objects[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.encode("utf-8")
        return {}

    def get_object(self, Bucket, Key):  # noqa: N803
        import io

        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix=""):  # noqa: N803
        keys = sorted(k for b, k in self.objects if b == Bucket and k.startswith(Prefix))
        yield {"Contents": [{"Key": k} for k in keys]} if keys else {}

    def keys(self, prefix: str = "") -> list[str]:
        return sorted(k for _, k in self.objects if k.startswith(prefix))


@pytest.fixture
def fake_s3():
    return FakeS3()


@pytest.fixture(scope="session")
def iceberg_spark(tmp_path_factory):
    """Iceberg 1.7.1(Glue 5.0과 같은 버전) + Hadoop 카탈로그 `glue_catalog`인 로컬 SparkSession.

    같은 프로세스에서 `spark` fixture와 함께 쓰지 않는다(먼저 만든 세션에는 jar가 붙지 않는다).
    iceberg 표시 테스트만 쓰고, `pytest -m iceberg`로 따로 실행한다.
    """
    import os
    import sys
    import time

    from pyspark.sql import SparkSession

    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ["TZ"] = "UTC"
    time.tzset()

    warehouse = tmp_path_factory.mktemp("iceberg-warehouse")
    session = (
        SparkSession.builder.master("local[2]")
        .appName("tms-silver-iceberg-tests")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.extraJavaOptions", "-Duser.timezone=UTC")
        .config("spark.jars.packages", "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.glue_catalog.type", "hadoop")
        .config("spark.sql.catalog.glue_catalog.warehouse", str(warehouse))
        .getOrCreate()
    )
    yield session
    session.stop()
