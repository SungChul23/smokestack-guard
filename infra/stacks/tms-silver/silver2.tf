# TW CEMS 공식 Silver·ML-ready (재수집 원본 기준). specs/a-platform/006-tw-cems-silver2-compare
# C가 다시 받은 원본(bronze2/tw_cems/)을 기존과 같은 규칙으로 silver2/에 만든다. 비교 결과 이쪽을 공식으로 정했다(2026-11-10).
# 기존 silver/ 리소스(Job, 역할, 테이블)는 옛 원본 기준이라 쓰지 않지만 정리 전까지 그대로 둔다.
# 경로 규칙: silver2/<테이블>/ = tms_silver2.<테이블> (AGENTS.md "S3 경로 규칙")

locals {
  bronze2_prefix         = "bronze2/tw_cems"
  silver2_table          = "silver2/tw_cems"
  silver2_runs           = "silver2/_runs/tw_cems"
  silver2_ml_ready_table = "silver2/tw_cems_ml_ready"
  silver2_ml_ready_runs  = "silver2/_runs/tw_cems_ml_ready"
  # 정답지(C가 bronze2로 만든 pandas 결과). Terraform 밖 버킷이며 compare 모드에서 읽기만 한다.
  silver2_reference_bucket = regex("^s3://([^/]+)/", var.silver2_ml_ready_reference)[0]
  silver2_reference_prefix = regex("^s3://[^/]+/(.*)/[^/]+$", var.silver2_ml_ready_reference)[0]
}

# ---------------------------------------------------------------------------
# Silver2 Job 역할. 기존 tms-glue-silver와 같은 모양이고 경로만 다르다.
# bronze2/tw_cems/는 읽기만, 쓰기·삭제는 silver2/tw_cems/와 실행 기록에만.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "silver2" {
  name = "tms-glue-silver2"
  # IAM 설명은 ASCII·Latin-1 문자만 허용한다(한글 불가).
  description        = "TW CEMS Silver2 Glue job role (bronze2 read, silver2/tw_cems write)"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "silver2_service" {
  role       = aws_iam_role.silver2.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "silver2_data" {
  statement {
    sid       = "ListRawScoped"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.bronze2_prefix}/*",
        local.silver2_table,
        "${local.silver2_table}/*",
        "${local.silver2_runs}/*",
      ]
    }
  }

  statement {
    sid       = "ReadBronze2TwCems"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/${local.bronze2_prefix}/*"]
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
    sid = "ReadWriteSilver2TwCems"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${local.raw_arn}/${local.silver2_table}/*",
      "${local.raw_arn}/${local.silver2_runs}/*",
    ]
  }

  # Glue(EMRFS) 폴더 표시 파일. silver2/* 로 넓히지 않고 정확한 키만 허용한다.
  statement {
    sid = "WriteSilver2FolderMarkers"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      "${local.raw_arn}/silver2_$folder$",
      "${local.raw_arn}/${local.silver2_table}_$folder$",
    ]
  }
}

resource "aws_iam_role_policy" "silver2_data" {
  name   = "tms-glue-silver2-data"
  role   = aws_iam_role.silver2.id
  policy = data.aws_iam_policy_document.silver2_data.json
}

# 스크립트와 패키지는 기존 Job과 같은 파일(ops/)을 쓴다. 규칙이 같아야 비교가 된다.
resource "aws_glue_job" "silver2_tw_cems" {
  name              = "tms-silver2-tw-cems"
  description       = "TW CEMS 재수집 원본(bronze2) 월 파일 1개를 Silver2(silver2/tw_cems)로 변환 (specs/a-platform/006-tw-cems-silver2-compare)"
  role_arn          = aws_iam_role.silver2.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = var.glue_worker_count
  timeout           = var.glue_timeout_minutes
  max_retries       = 0 # 재시도는 run_silver.py가 1회만 한다
  execution_class   = "STANDARD"

  execution_property {
    max_concurrent_runs = 6
  }

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${local.raw_bucket}/${aws_s3_object.job_script.key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = aws_cloudwatch_log_group.glue.name
    "--enable-metrics"                   = "true"
    "--extra-py-files"                   = "s3://${local.raw_bucket}/${aws_s3_object.package.key}"
    "--raw_bucket"                       = local.raw_bucket
    "--raw_prefix"                       = local.bronze2_prefix
    "--silver_bucket"                    = local.raw_bucket
    "--table_prefix"                     = local.silver2_table
    "--runs_prefix"                      = local.silver2_runs
    "--package_md5"                      = data.archive_file.package.output_md5
  }
}

# ---------------------------------------------------------------------------
# ML-ready2. silver2/tw_cems/를 읽어 silver2/tw_cems_ml_ready/를 만든다.
# compare는 C가 같은 bronze2로 만든 pandas 결과(var.silver2_ml_ready_reference)와 35컬럼을 비교한다.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "silver2_ml_ready" {
  name = "tms-glue-silver2-ml-ready"
  # IAM 설명은 ASCII·Latin-1 문자만 허용한다(한글 불가).
  description        = "TW CEMS ML-ready2 Glue job role (silver2/tw_cems read, silver2/tw_cems_ml_ready write)"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "silver2_ml_ready_service" {
  role       = aws_iam_role.silver2_ml_ready.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "silver2_ml_ready_data" {
  statement {
    sid       = "ListRawScoped"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.silver2_table,
        "${local.silver2_table}/*",
        local.silver2_ml_ready_table,
        "${local.silver2_ml_ready_table}/*",
        "${local.silver2_ml_ready_runs}/*",
      ]
    }
  }

  # 입력 Silver2는 읽기만.
  statement {
    sid       = "ReadSilver2TwCems"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/${local.silver2_table}/*"]
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
    sid = "ReadWriteMlReady2"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${local.raw_arn}/${local.silver2_ml_ready_table}/*",
      "${local.raw_arn}/${local.silver2_ml_ready_runs}/*",
    ]
  }

  statement {
    sid       = "WriteMlReady2FolderMarker"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.raw_arn}/${local.silver2_ml_ready_table}_$folder$"]
  }

  # 상위 표시 파일은 Silver2 Job과 함께 쓴다. 삭제 권한은 주지 않는다.
  statement {
    sid       = "WriteSilver2FolderMarker"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${local.raw_arn}/silver2_$folder$"]
  }

  statement {
    sid       = "ListReference"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${local.silver2_reference_bucket}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [local.silver2_reference_prefix, "${local.silver2_reference_prefix}/*"]
    }
  }

  statement {
    sid       = "ReadReference"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${local.silver2_reference_bucket}/${local.silver2_reference_prefix}/*"]
  }
}

resource "aws_iam_role_policy" "silver2_ml_ready_data" {
  name   = "tms-glue-silver2-ml-ready-data"
  role   = aws_iam_role.silver2_ml_ready.id
  policy = data.aws_iam_policy_document.silver2_ml_ready_data.json
}

resource "aws_glue_job" "silver2_tw_cems_ml_ready" {
  name              = "tms-silver2-tw-cems-ml-ready"
  description       = "TW CEMS Silver2(silver2/tw_cems) 전체를 ML-ready2(silver2/tw_cems_ml_ready)로 변환·비교 (specs/a-platform/006-tw-cems-silver2-compare)"
  role_arn          = aws_iam_role.silver2_ml_ready.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = var.ml_ready_worker_count
  timeout           = 60
  max_retries       = 0
  execution_class   = "STANDARD"

  execution_property {
    max_concurrent_runs = 1
  }

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${local.raw_bucket}/${aws_s3_object.ml_ready_script.key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = aws_cloudwatch_log_group.glue.name
    "--enable-metrics"                   = "true"
    "--extra-py-files"                   = "s3://${local.raw_bucket}/${aws_s3_object.package.key},s3://${local.raw_bucket}/${aws_s3_object.ml_ready_module.key}"
    "--mode"                             = "build"
    "--bucket"                           = local.raw_bucket
    "--source_prefix"                    = local.silver2_table
    "--table_prefix"                     = local.silver2_ml_ready_table
    "--runs_prefix"                      = local.silver2_ml_ready_runs
    "--files"                            = "6"
    "--reference"                        = var.silver2_ml_ready_reference
    "--package_md5"                      = data.archive_file.package.output_md5
  }
}

# ---------------------------------------------------------------------------
# 카탈로그 tms_silver2. 컬럼은 main.tf의 locals를 그대로 쓴다.
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "silver2" {
  name        = "tms_silver2"
  description = "TW CEMS 공식 Silver (재수집 원본 bronze2 기준). 경로 규칙 silver2/<테이블>/ = tms_silver2.<테이블> (specs/a-platform/006-tw-cems-silver2-compare)"
}

resource "aws_glue_catalog_table" "silver2_tw_cems" {
  name          = "tw_cems"
  database_name = aws_glue_catalog_database.silver2.name
  description   = "TW CEMS 30분 슬롯 Silver2 (bronze2 입력, 규칙은 tms_silver.tw_cems와 같음)"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"            = "parquet"
    "EXTERNAL"                  = "TRUE"
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2023,2030"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "1,12"
    "projection.month.digits"   = "2"
    "storage.location.template" = "s3://${local.raw_bucket}/${local.silver2_table}/year=$${year}/month=$${month}/"
  }

  partition_keys {
    name = "year"
    type = "string"
  }

  partition_keys {
    name = "month"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${local.raw_bucket}/${local.silver2_table}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = local.silver_columns

      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}

resource "aws_glue_catalog_table" "silver2_tw_cems_ml_ready" {
  name          = "tw_cems_ml_ready"
  database_name = aws_glue_catalog_database.silver2.name
  description   = "TW CEMS ML-ready2 35컬럼 (silver2 입력). 읽기 전에 silver2/_runs/tw_cems_ml_ready/latest.json 존재 확인"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
    "EXTERNAL"       = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.raw_bucket}/${local.silver2_ml_ready_table}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = local.ml_ready_columns

      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}
