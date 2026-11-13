# K-TMS Silver·ML-ready 매일 갱신 파이프라인. specs/a-platform/008-ktms-silver-pipeline
#
# tms_cleansys/(수집 원본, 읽기만) → Silver(tms_silver2.ktms) → ML-ready(tms_silver2.ktms_ml_ready)
# EventBridge Scheduler(매일 03:00 KST) → Step Functions → Glue 5.0 Job 2개(Silver → ML-ready)
#
# - 계산은 C의 src/smokestack_guard/silver(ktms.py, ml_ready.py)를 수정 없이 zip으로 배포해 쓴다(기존 package).
# - 두 테이블은 Iceberg다. 테이블은 Terraform이 아니라 잡의 DDL(CREATE TABLE IF NOT EXISTS)이 만든다.
#   Iceberg가 커밋마다 카탈로그의 metadata_location을 바꾸기 때문이다(plan Complexity Tracking, research R3).
# - 원본(tms_cleansys/)에는 어떤 역할도 쓰기·삭제 권한이 없다(원칙 I).
# - 합성(tms_synthetic/)용 잡·권한은 아직 만들지 않는다(research R9).

locals {
  ktms_silver_table     = "silver2/ktms"
  ktms_silver_runs      = "silver2/_runs/ktms"
  ktms_ml_ready_table   = "silver2/ktms_ml_ready"
  ktms_ml_ready_runs    = "silver2/_runs/ktms_ml_ready"
  ktms_source_prefix    = "tms_cleansys"
  ktms_services_dir     = "${path.module}/../../../services/tms-silver"
  ktms_glue_catalog     = "arn:aws:glue:ap-northeast-2:${data.aws_caller_identity.current.account_id}"
  ktms_silver_catalog   = "tms_silver2.ktms"
  ktms_ml_ready_catalog = "tms_silver2.ktms_ml_ready"

  # Glue 5.0 내장 Iceberg 1.7.1을 카탈로그 이름 glue_catalog로 연다. 코드의 테이블 식별자는 glue_catalog.<db>.<table>.
  ktms_iceberg_conf = join(" --conf ", [
    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog",
    "spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog",
    "spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO",
    "spark.sql.catalog.glue_catalog.warehouse=s3://${local.raw_bucket}/silver2/",
    "spark.sql.session.timeZone=UTC",
  ])

  ktms_common_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = aws_cloudwatch_log_group.glue.name
    "--datalake-formats"                 = "iceberg"
    "--conf"                             = local.ktms_iceberg_conf
    "--extra-py-files"                   = "s3://${local.raw_bucket}/${aws_s3_object.package.key},s3://${local.raw_bucket}/${aws_s3_object.ktms_pipeline.key}"
    "--bucket"                           = local.raw_bucket
    "--silver_table"                     = local.ktms_silver_catalog
    "--package_md5"                      = data.archive_file.package.output_md5
    "--start_date"                       = "auto"
    "--end_date"                         = "auto"
    "--sfn_execution"                    = "manual"
  }
}

data "aws_caller_identity" "current" {}

# 알림은 수집 스택의 토픽을 같이 쓴다. 이메일 구독은 그 스택이 관리한다.
data "aws_sns_topic" "alerts" {
  name = "tms-collector-alerts"
}

# ---------------------------------------------------------------------------
# 운영 파일
# ---------------------------------------------------------------------------

resource "aws_s3_object" "ktms_pipeline" {
  bucket = local.raw_bucket
  key    = "ops/glue-packages/ktms_pipeline.py"
  source = "${local.ktms_services_dir}/ktms_pipeline.py"
  etag   = filemd5("${local.ktms_services_dir}/ktms_pipeline.py")
}

resource "aws_s3_object" "ktms_silver_script" {
  bucket = local.raw_bucket
  key    = "ops/glue-scripts/glue_ktms_silver.py"
  source = "${local.ktms_services_dir}/glue_ktms_silver.py"
  etag   = filemd5("${local.ktms_services_dir}/glue_ktms_silver.py")
}

resource "aws_s3_object" "ktms_ml_ready_script" {
  bucket = local.raw_bucket
  key    = "ops/glue-scripts/glue_ktms_ml_ready.py"
  source = "${local.ktms_services_dir}/glue_ktms_ml_ready.py"
  etag   = filemd5("${local.ktms_services_dir}/glue_ktms_ml_ready.py")
}

# ---------------------------------------------------------------------------
# Silver Job 역할: tms_cleansys/ 읽기, silver2/ktms/와 실행 기록 쓰기
# ---------------------------------------------------------------------------

resource "aws_iam_role" "ktms_silver" {
  name = "tms-glue-silver2-ktms"
  # IAM 설명은 ASCII·Latin-1 문자만 허용한다(한글 불가).
  description        = "K-TMS Silver Glue job role (tms_cleansys read, silver2/ktms Iceberg write)"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "ktms_silver_service" {
  role       = aws_iam_role.ktms_silver.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "ktms_silver_data" {
  statement {
    sid       = "ListRawScoped"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.ktms_source_prefix}/*",
        local.ktms_silver_table,
        "${local.ktms_silver_table}/*",
        "${local.ktms_silver_runs}/*",
      ]
    }
  }

  statement {
    sid       = "ReadKtmsBronze"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/${local.ktms_source_prefix}/*"]
  }

  statement {
    sid     = "ReadOps"
    actions = ["s3:GetObject"]
    resources = [
      "${local.raw_arn}/ops/glue-scripts/*",
      "${local.raw_arn}/ops/glue-packages/*",
    ]
  }

  # 삭제는 Iceberg가 실패한 커밋의 미사용 파일을 지울 때만 쓴다. 오래된 버전 정리는 하지 않는다.
  statement {
    sid = "ReadWriteKtmsSilver"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${local.raw_arn}/${local.ktms_silver_table}/*",
      "${local.raw_arn}/${local.ktms_silver_runs}/*",
    ]
  }

  # AWSGlueServiceRole에도 들어 있지만, 이 잡이 쓰는 카탈로그 범위를 명시한다.
  statement {
    sid = "IcebergCatalogKtms"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:CreateTable",
      "glue:UpdateTable",
    ]
    resources = [
      "${local.ktms_glue_catalog}:catalog",
      "${local.ktms_glue_catalog}:database/tms_silver2",
      "${local.ktms_glue_catalog}:table/tms_silver2/ktms",
    ]
  }
}

resource "aws_iam_role_policy" "ktms_silver_data" {
  name   = "tms-glue-silver2-ktms-data"
  role   = aws_iam_role.ktms_silver.id
  policy = data.aws_iam_policy_document.ktms_silver_data.json
}

# ---------------------------------------------------------------------------
# ML-ready Job 역할: silver2/ktms/ 읽기, silver2/ktms_ml_ready/와 실행 기록 쓰기. 원본 권한 없음
# ---------------------------------------------------------------------------

resource "aws_iam_role" "ktms_ml_ready" {
  name               = "tms-glue-silver2-ktms-ml-ready"
  description        = "K-TMS ML-ready Glue job role (silver2/ktms read, silver2/ktms_ml_ready Iceberg write)"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "ktms_ml_ready_service" {
  role       = aws_iam_role.ktms_ml_ready.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "ktms_ml_ready_data" {
  statement {
    sid       = "ListRawScoped"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.ktms_silver_table,
        "${local.ktms_silver_table}/*",
        local.ktms_ml_ready_table,
        "${local.ktms_ml_ready_table}/*",
        "${local.ktms_ml_ready_runs}/*",
      ]
    }
  }

  statement {
    sid       = "ReadKtmsSilver"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/${local.ktms_silver_table}/*"]
  }

  statement {
    sid     = "ReadOps"
    actions = ["s3:GetObject"]
    resources = [
      "${local.raw_arn}/ops/glue-scripts/*",
      "${local.raw_arn}/ops/glue-packages/*",
    ]
  }

  statement {
    sid = "ReadWriteKtmsMlReady"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${local.raw_arn}/${local.ktms_ml_ready_table}/*",
      "${local.raw_arn}/${local.ktms_ml_ready_runs}/*",
    ]
  }

  statement {
    sid     = "IcebergCatalogReadSilver"
    actions = ["glue:GetDatabase", "glue:GetTable"]
    resources = [
      "${local.ktms_glue_catalog}:catalog",
      "${local.ktms_glue_catalog}:database/tms_silver2",
      "${local.ktms_glue_catalog}:table/tms_silver2/ktms",
    ]
  }

  statement {
    sid = "IcebergCatalogMlReady"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:CreateTable",
      "glue:UpdateTable",
    ]
    resources = [
      "${local.ktms_glue_catalog}:catalog",
      "${local.ktms_glue_catalog}:database/tms_silver2",
      "${local.ktms_glue_catalog}:table/tms_silver2/ktms_ml_ready",
    ]
  }
}

resource "aws_iam_role_policy" "ktms_ml_ready_data" {
  name   = "tms-glue-silver2-ktms-ml-ready-data"
  role   = aws_iam_role.ktms_ml_ready.id
  policy = data.aws_iam_policy_document.ktms_ml_ready_data.json
}

# ---------------------------------------------------------------------------
# Glue Job. 동시 실행 1: 같은 테이블에 두 실행이 쓰지 않는다(FR-015).
# ---------------------------------------------------------------------------

resource "aws_glue_job" "ktms_silver" {
  name              = "tms-silver2-ktms"
  description       = "K-TMS Silver (tms_cleansys -> tms_silver2.ktms Iceberg). spec 008"
  role_arn          = aws_iam_role.ktms_silver.arn
  glue_version      = "5.0"
  worker_type       = var.ktms_worker_type
  number_of_workers = var.ktms_worker_count
  timeout           = 60
  max_retries       = 0 # 재시도는 Step Functions가 한다

  execution_property {
    max_concurrent_runs = 1
  }

  command {
    name            = "glueetl"
    script_location = "s3://${local.raw_bucket}/${aws_s3_object.ktms_silver_script.key}"
    python_version  = "3"
  }

  default_arguments = merge(local.ktms_common_arguments, {
    "--source_prefix" = "${local.ktms_source_prefix}/"
    "--runs_prefix"   = local.ktms_silver_runs
    "--max_days"      = "7"
  })
}

resource "aws_glue_job" "ktms_ml_ready" {
  name              = "tms-silver2-ktms-ml-ready"
  description       = "K-TMS ML-ready (tms_silver2.ktms -> tms_silver2.ktms_ml_ready Iceberg). spec 008"
  role_arn          = aws_iam_role.ktms_ml_ready.arn
  glue_version      = "5.0"
  worker_type       = var.ktms_worker_type
  number_of_workers = var.ktms_worker_count
  timeout           = 60
  max_retries       = 0

  execution_property {
    max_concurrent_runs = 1
  }

  command {
    name            = "glueetl"
    script_location = "s3://${local.raw_bucket}/${aws_s3_object.ktms_ml_ready_script.key}"
    python_version  = "3"
  }

  default_arguments = merge(local.ktms_common_arguments, {
    "--ml_ready_table" = local.ktms_ml_ready_catalog
    "--runs_prefix"    = local.ktms_ml_ready_runs
  })
}

# ---------------------------------------------------------------------------
# Step Functions: Silver → ML-ready, 단계마다 재시도 1회, 실패 시 SNS (research R8)
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ktms_sfn" {
  name               = "tms-sfn-silver2-ktms"
  description        = "K-TMS silver2 state machine role (start Glue jobs, publish failure alert)"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "ktms_sfn" {
  statement {
    sid = "RunKtmsGlueJobs"
    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun",
    ]
    resources = [
      aws_glue_job.ktms_silver.arn,
      aws_glue_job.ktms_ml_ready.arn,
    ]
  }

  statement {
    sid       = "PublishAlert"
    actions   = ["sns:Publish"]
    resources = [data.aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "ktms_sfn" {
  name   = "tms-sfn-silver2-ktms"
  role   = aws_iam_role.ktms_sfn.id
  policy = data.aws_iam_policy_document.ktms_sfn.json
}

resource "aws_sfn_state_machine" "ktms" {
  name     = "tms-silver2-ktms"
  type     = "STANDARD"
  role_arn = aws_iam_role.ktms_sfn.arn
  definition = templatefile("${path.module}/ktms_pipeline.asl.json", {
    silver_job   = aws_glue_job.ktms_silver.name
    ml_ready_job = aws_glue_job.ktms_ml_ready.name
    topic_arn    = data.aws_sns_topic.alerts.arn
    bucket       = local.raw_bucket
  })
}

# ---------------------------------------------------------------------------
# 매일 03:00 KST. 전체 생성(quickstart §3)이 끝나기 전에는 꺼 둔다(var.ktms_schedule_enabled).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ktms_scheduler" {
  name               = "tms-scheduler-silver2-ktms"
  description        = "Starts the K-TMS silver2 state machine every day at 03:00 KST"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "ktms_scheduler" {
  statement {
    sid       = "StartKtmsStateMachine"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.ktms.arn]
  }
}

resource "aws_iam_role_policy" "ktms_scheduler" {
  name   = "tms-scheduler-silver2-ktms"
  role   = aws_iam_role.ktms_scheduler.id
  policy = data.aws_iam_policy_document.ktms_scheduler.json
}

resource "aws_scheduler_schedule" "ktms_daily" {
  name                         = "tms-silver2-ktms-daily"
  description                  = "K-TMS Silver/ML-ready daily rebuild of the last 2 complete KST days (spec 008)"
  schedule_expression          = "cron(0 3 * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"
  state                        = var.ktms_schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.ktms.arn
    role_arn = aws_iam_role.ktms_scheduler.arn
    input    = jsonencode({})
  }
}
