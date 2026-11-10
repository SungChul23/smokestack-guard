# TW CEMS Silver 실행. specs/a-platform/004-tw-cems-silver-glue
# 원본 JSONL을 C의 Silver 규칙(src/smokestack_guard/silver)으로 변환해 원본 버킷의 silver/tw_cems/에 쓴다.

# 원본 버킷은 tms-collection 스택이 관리한다. 여기서는 이름으로 참조만 한다.
# 버전 관리, 수명 주기, 버킷 정책 등 어떤 설정도 붙이지 않는다(원칙 I, research R11).
data "aws_s3_bucket" "raw" {
  bucket = var.raw_bucket_name
}

locals {
  raw_bucket   = data.aws_s3_bucket.raw.id
  raw_arn      = data.aws_s3_bucket.raw.arn
  silver_table = "silver/tw_cems"
  silver_runs  = "silver/_runs/tw_cems"
}

# ---------------------------------------------------------------------------
# 운영 파일 업로드. 원본 버킷의 ops/에는 Terraform이 올리는 운영 파일만 둔다(research R10).
# ---------------------------------------------------------------------------

# C의 규칙 코드를 그대로 묶는다. data/는 없는 모듈(collector)을 import하므로 뺀다(research R5).
data "archive_file" "package" {
  type             = "zip"
  source_dir       = "${path.module}/../../../src"
  output_path      = "${path.module}/../../../services/tms-silver/build/smokestack_guard.zip"
  output_file_mode = "0666"
  excludes = [
    "smokestack_guard/data/**",
    "**/__pycache__/**",
    "**/*.pyc",
  ]
}

resource "aws_s3_object" "package" {
  bucket = local.raw_bucket
  key    = "ops/glue-packages/smokestack_guard.zip"
  source = data.archive_file.package.output_path
  etag   = data.archive_file.package.output_md5
}

resource "aws_s3_object" "job_script" {
  bucket = local.raw_bucket
  key    = "ops/glue-scripts/glue_tw_cems_silver.py"
  source = "${path.module}/../../../services/tms-silver/glue_tw_cems_silver.py"
  etag   = filemd5("${path.module}/../../../services/tms-silver/glue_tw_cems_silver.py")
}

# ---------------------------------------------------------------------------
# Glue 실행 역할. 팀 PassRole 정책상 이름은 tms- 로 시작한다.
# 원본 버킷에 쓰기·삭제 권한을 가진 첫 실행 주체라 경로를 silver/tw_cems로만 좁힌다(research R12).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name = "tms-glue-silver"
  # IAM 설명은 ASCII·Latin-1 문자만 허용한다(한글 불가).
  description        = "TW CEMS Silver Glue job role (bronze read, silver/tw_cems write)"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

# 카탈로그, /aws-glue/* 로그, 지표.
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_data" {
  # 버킷 전체 목록 권한은 주지 않는다. Spark 덮어쓰기는 끝에 / 가 없는 접두어로도 조회하므로 silver/tw_cems를 넣는다.
  statement {
    sid       = "ListRawScoped"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "bronze/tw_cems/*",
        local.silver_table,
        "${local.silver_table}/*",
        "${local.silver_runs}/*",
      ]
    }
  }

  # 원본: 읽기만. 쓰기·삭제 권한은 주지 않는다.
  statement {
    sid       = "ReadBronzeTwCems"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/bronze/tw_cems/*"]
  }

  statement {
    sid     = "ReadOps"
    actions = ["s3:GetObject"]
    resources = [
      "${local.raw_arn}/ops/glue-scripts/*",
      "${local.raw_arn}/ops/glue-packages/*",
    ]
  }

  # 월 단위 파티션 교체와 실행 기록에 삭제가 필요하다. 이 두 경로 밖에는 쓰지 못한다.
  statement {
    sid = "ReadWriteSilverTwCems"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${local.raw_arn}/${local.silver_table}/*",
      "${local.raw_arn}/${local.silver_runs}/*",
    ]
  }

  # Glue(EMRFS)는 Parquet을 쓸 때 상위 경로마다 0바이트 "<경로>_$folder$" 표시 파일을 만든다.
  # silver/tw_cems/ 아래 표시는 위 문장에 포함되고, 그 위 두 개만 정확한 키로 허용한다(silver/* 로 넓히지 않음).
  # 2026-11-09 첫 실행에서 silver_$folder$ PutObject 거부로 확인했다.
  statement {
    sid = "WriteSilverFolderMarkers"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      "${local.raw_arn}/silver_$folder$",
      "${local.raw_arn}/${local.silver_table}_$folder$",
    ]
  }
}

resource "aws_iam_role_policy" "glue_data" {
  name   = "tms-glue-silver-data"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_data.json
}

# 연속 로그 전용 그룹. 계정의 공용 /aws-glue/jobs/* 그룹은 건드리지 않는다.
resource "aws_cloudwatch_log_group" "glue" {
  name              = "/aws-glue/tms-silver"
  retention_in_days = 14
}

# ---------------------------------------------------------------------------
# 카탈로그. 경로 규칙: silver/<테이블>/ = tms_silver.<테이블> (AGENTS.md "S3 경로 규칙")
# 파티션 프로젝션이라 새 월도 크롤러 없이 Athena에서 보인다. Spark는 카탈로그가 아니라 S3 경로로 읽는다.
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "silver" {
  name        = "tms_silver"
  description = "Silver 테이블. 경로 규칙 silver/<테이블>/ = tms_silver.<테이블> (specs/a-platform/004-tw-cems-silver-glue)"
}

resource "aws_glue_catalog_table" "tw_cems" {
  name          = "tw_cems"
  database_name = aws_glue_catalog_database.silver.name
  description   = "TW CEMS 30분 슬롯 Silver (계약: specs/c-contract/201-tw-cems-silver). Spark는 카탈로그가 아니라 S3 경로로 읽는다(프로젝션은 Athena 전용)"
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
    "storage.location.template" = "s3://${local.raw_bucket}/${local.silver_table}/year=$${year}/month=$${month}/"
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
    location      = "s3://${local.raw_bucket}/${local.silver_table}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    # 순서와 타입은 data-model.md §2와 같다.
    dynamic "columns" {
      for_each = [
        ["area_nm", "string"],
        ["fact_manage_nm", "string"],
        ["stack_code", "string"],
        ["item", "string"],
        ["unit", "string"],
        ["value", "double"],
        ["limit", "double"],
        ["status", "string"],
        ["ts_kst", "timestamp"],
        ["ratio", "double"],
        ["ts_local", "timestamp"],
        ["code2", "string"],
        ["flag_code_ratio_mismatch", "boolean"],
      ]

      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Silver Job. 한 실행 = 한 달. --year, --month는 실행 때마다 run_silver.py가 넘긴다(기본값 없음).
# Glue 5.0(Spark 3.5.4)은 C의 로컬 검증 환경과 같은 Spark 버전이다(research R1).
# --TempDir은 주지 않는다. Parquet 쓰기에는 필요 없고, 원본 버킷에 임시 경로를 만들지 않기 위해서다(research R11).
# ---------------------------------------------------------------------------

resource "aws_glue_job" "tw_cems" {
  name              = "tms-silver-tw-cems"
  description       = "TW CEMS 원본 월 파일 1개를 Silver(silver/tw_cems)로 변환 (specs/a-platform/004-tw-cems-silver-glue)"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = var.glue_worker_count
  timeout           = var.glue_timeout_minutes
  max_retries       = 0 # 재시도는 run_silver.py가 1회만 한다
  execution_class   = "STANDARD"

  execution_property {
    max_concurrent_runs = 6 # 동시 6 × 10 DPU = 60 DPU
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
    "--raw_prefix"                       = "bronze/tw_cems/historical"
    "--silver_bucket"                    = local.raw_bucket
    "--table_prefix"                     = local.silver_table
    "--runs_prefix"                      = local.silver_runs
    "--package_md5"                      = data.archive_file.package.output_md5
  }
}
