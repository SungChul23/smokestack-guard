# TW CEMS Athena EDA 환경. specs/a-platform/003-tw-cems-eda
# 원본 JSONL을 1회 Parquet으로 바꿔 Athena로 조회한다. Silver·ML은 이 리소스에 의존하지 않는다.

# 원본 버킷은 tms-collection 스택이 관리한다. 여기서는 이름으로 참조만 하고 어떤 설정도 붙이지 않는다.
data "aws_s3_bucket" "raw" {
  bucket = var.raw_bucket_name
}

# ---------------------------------------------------------------------------
# EDA 버킷: 원본에서 다시 만들 수 있는 파생본만 둔다.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "eda" {
  bucket = var.eda_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "eda" {
  bucket = aws_s3_bucket.eda.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "eda" {
  bucket = aws_s3_bucket.eda.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "eda" {
  bucket = aws_s3_bucket.eda.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "eda" {
  bucket = aws_s3_bucket.eda.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 버전 관리가 켜져 있어 덮어쓴 객체가 이전 버전으로 남는다. 파생본이므로 이전 버전도 정리한다.
# 이 규칙은 EDA 버킷에만 적용한다. 원본 버킷에는 수명 주기 규칙을 두지 않는다(원칙 I).
resource "aws_s3_bucket_lifecycle_configuration" "eda" {
  bucket = aws_s3_bucket.eda.id

  rule {
    id     = "athena-results-30d"
    status = "Enabled"

    filter {
      prefix = "athena-results/"
    }

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }

  rule {
    id     = "glue-temp-7d"
    status = "Enabled"

    filter {
      prefix = "glue-temp/"
    }

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }

  # 월 단위 덮어쓰기로 지워진 Parquet(이전 버전)은 7일 뒤 정리한다. 현재 버전은 만료하지 않는다.
  rule {
    id     = "tw-cems-raw-noncurrent-7d"
    status = "Enabled"

    filter {
      prefix = "tw_cems_raw/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    expiration {
      expired_object_delete_marker = true
    }
  }

  rule {
    id     = "abort-incomplete-multipart-7d"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.eda]
}

# ---------------------------------------------------------------------------
# Glue 실행 역할 (Job과 크롤러가 함께 사용). 팀 PassRole 정책상 이름은 tms- 로 시작한다.
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
  name = "tms-glue-eda"
  # IAM 설명은 ASCII·Latin-1 문자만 허용한다(한글 불가).
  description        = "TW CEMS EDA Glue job and crawler role (raw bucket read-only)"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

# 카탈로그, /aws-glue/* 로그, 지표. aws-glue-* 버킷 접근도 포함되지만 이 기능은 쓰지 않는다.
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_data" {
  # 원본: bronze/tw_cems/ 아래 목록 조회와 읽기만. 쓰기·삭제 권한은 주지 않는다.
  statement {
    sid       = "ListRawTwCems"
    actions   = ["s3:ListBucket"]
    resources = [data.aws_s3_bucket.raw.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["bronze/tw_cems/*"]
    }
  }

  statement {
    sid       = "ReadRawTwCems"
    actions   = ["s3:GetObject"]
    resources = ["${data.aws_s3_bucket.raw.arn}/bronze/tw_cems/*"]
  }

  # EDA 전용 버킷이라 목록 조회는 경로 조건 없이 허용한다.
  # Spark 덮어쓰기와 크롤러가 접두어 끝에 / 가 없는 형태로도 조회하기 때문이다.
  statement {
    sid       = "ListEda"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.eda.arn]
  }

  # 월 단위 덮어쓰기에 삭제가 필요하다.
  statement {
    sid = "ReadWriteEdaData"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${aws_s3_bucket.eda.arn}/tw_cems_raw/*",
      "${aws_s3_bucket.eda.arn}/glue-temp/*",
    ]
  }

  statement {
    sid       = "ReadGlueScripts"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.eda.arn}/glue-scripts/*"]
  }
}

resource "aws_iam_role_policy" "glue_data" {
  name   = "tms-glue-eda-data"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_data.json
}

# 연속 로그 전용 그룹. 계정의 공용 /aws-glue/jobs/* 그룹은 다른 리소스와 공유하므로 건드리지 않는다.
resource "aws_cloudwatch_log_group" "glue" {
  name              = "/aws-glue/tms-eda"
  retention_in_days = 14
}

# ---------------------------------------------------------------------------
# 변환 Job. Job을 늘릴 때는 glue_jobs에 항목 하나만 추가한다.
# ---------------------------------------------------------------------------

locals {
  glue_jobs = {
    "tms-eda-tw-cems-parquet" = {
      script         = "tw_cems_parquet.py"
      workers        = var.glue_worker_count # G.1X, 1워커 = 1 DPU
      timeout        = 30                    # 분
      max_concurrent = 6                     # 동시 6 × 10 DPU = 60 DPU (계정 한도 500)
      # --year, --month는 실행 때마다 run_backfill.py가 넘긴다. 기본값을 두지 않는다.
      arguments = {
        "--raw_bucket"    = var.raw_bucket_name
        "--raw_prefix"    = "bronze/tw_cems/historical"
        "--eda_bucket"    = var.eda_bucket_name
        "--output_prefix" = "tw_cems_raw"
      }
    }
  }

  glue_common_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--TempDir"                          = "s3://${aws_s3_bucket.eda.id}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = aws_cloudwatch_log_group.glue.name
    "--enable-metrics"                   = "true"
  }
}

# 스크립트가 바뀌면 etag가 달라져 다시 올라간다.
resource "aws_s3_object" "job_script" {
  for_each = local.glue_jobs

  bucket = aws_s3_bucket.eda.id
  key    = "glue-scripts/${each.value.script}"
  source = "${path.module}/../../../services/tms-eda/${each.value.script}"
  etag   = filemd5("${path.module}/../../../services/tms-eda/${each.value.script}")
}

resource "aws_glue_job" "this" {
  for_each = local.glue_jobs

  name              = each.key
  description       = "TW CEMS 원본 월 파일 1개를 Athena EDA용 Parquet으로 변환 (Silver 입력 아님)"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "6.0"
  worker_type       = "G.1X"
  number_of_workers = each.value.workers
  timeout           = each.value.timeout
  max_retries       = 0 # 재시도는 run_backfill.py가 1회만 한다
  execution_class   = "STANDARD"

  execution_property {
    max_concurrent_runs = each.value.max_concurrent
  }

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${aws_s3_bucket.eda.id}/${aws_s3_object.job_script[each.key].key}"
  }

  default_arguments = merge(local.glue_common_arguments, each.value.arguments)
}

# ---------------------------------------------------------------------------
# 카탈로그와 조회
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "eda" {
  name        = "tms_eda"
  description = "TW CEMS Athena EDA 전용. Silver 입력 아님 (specs/a-platform/003-tw-cems-eda)"
}

# 수동 실행 전용(schedule 없음). 백필이 끝난 뒤 사람이 시작한다.
# 월마다 키 구성이 달라도 테이블 하나(tw_cems_raw)로 합친다.
resource "aws_glue_crawler" "tw_cems_raw" {
  name          = "tms-eda-tw-cems-crawler"
  description   = "tw_cems_raw/ Parquet을 tms_eda.tw_cems_raw 테이블 하나로 등록"
  role          = aws_iam_role.glue.arn
  database_name = aws_glue_catalog_database.eda.name

  s3_target {
    path       = "s3://${aws_s3_bucket.eda.id}/tw_cems_raw/"
    exclusions = ["**/_SUCCESS"]
  }

  recrawl_policy {
    recrawl_behavior = "CRAWL_EVERYTHING"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  configuration = jsonencode({
    Version  = 1.0
    Grouping = { TableGroupingPolicy = "CombineCompatibleSchemas" }
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
    }
  })
}

# 쿼리당 스캔 한도를 강제한다. 사용자가 클라이언트 설정으로 한도를 풀 수 없다.
resource "aws_athena_workgroup" "eda" {
  name        = "tms-eda"
  description = "TW CEMS EDA 조회 전용 (쿼리당 스캔 한도 적용)"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    result_configuration {
      output_location = "s3://${aws_s3_bucket.eda.id}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
