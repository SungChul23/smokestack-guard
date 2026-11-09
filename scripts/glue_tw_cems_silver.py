"""Glue job: raw Taiwan CEMS JSON Lines -> silver parquet (year/month partitions).

Parameters: --source s3://.../bronze/tw_cems/historical/2025-10.jsonl  --output s3://.../silver/tw_cems/
Needs `--extra-py-files smokestack_guard.zip` (zip of src/smokestack_guard). See spark_migration_checklist.md.
"""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

from smokestack_guard.silver import tw_cems_spark

args = getResolvedOptions(sys.argv, ["JOB_NAME", "source", "output"])
sc = SparkContext.getOrCreate()
glue = GlueContext(sc)
spark = glue.spark_session
spark.conf.set("spark.sql.session.timeZone", "UTC")
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

job = Job(glue)
job.init(args["JOB_NAME"], args)
tw_cems_spark.build(spark, args["source"], args["output"])
job.commit()
