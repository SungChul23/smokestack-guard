# K-TMS ML-ready 계약 검사 단계. specs/a-platform/010-ml-ready-contract-check
#
# 상태 머신 tms-silver2-ktms의 ML-ready 다음 단계에서 Lambda가 같은 범위·스냅샷의 ktms_ml_ready를 Athena로 읽어
# C의 계약 검사 규칙(src/smokestack_guard/silver/ml_ready_check.py)으로 판정한다.
#
# - 읽기 전용: 테이블·원본 경로 쓰기 권한이 없다. 쓰는 곳은 자기 실행 기록과 Athena 결과 경로뿐이다(FR-012).
# - 알림은 Lambda가 아니라 상태 머신이 보낸다(이 역할에 SNS 발행 권한 없음, research R7).
# - 규칙 코드는 Glue가 쓰는 같은 zip(data.archive_file.package)을 레이어로 쓴다(research R2).
# - 합성 테이블 검사 권한은 합성 통합 작업에서 더한다(US4).

locals {
  ktms_check_name = "tms-ktms-ml-ready-check"
  ktms_check_runs = "silver2/_runs/ktms_ml_ready_check"
  eda_arn         = "arn:aws:s3:::${var.eda_bucket_name}"
}

# 진입점 + 008 공통 모듈(범위 계산·실행 기록). 규칙 패키지는 레이어로 붙는다.
data "archive_file" "ktms_check" {
  type             = "zip"
  output_path      = "${local.ktms_services_dir}/build/ktms_ml_ready_check.zip"
  output_file_mode = "0666"

  source {
    content  = file("${local.ktms_services_dir}/lambda_ktms_ml_ready_check.py")
    filename = "lambda_ktms_ml_ready_check.py"
  }

  source {
    content  = file("${local.ktms_services_dir}/ktms_pipeline.py")
    filename = "ktms_pipeline.py"
  }
}

resource "aws_lambda_layer_version" "rules" {
  layer_name          = "tms-smokestack-guard-rules"
  description         = "C rules package (src/smokestack_guard), same zip as the Glue jobs"
  filename            = data.archive_file.package.output_path
  source_code_hash    = data.archive_file.package.output_base64sha256
  compatible_runtimes = ["python3.12"]
}

resource "aws_cloudwatch_log_group" "ktms_check" {
  name              = "/aws/lambda/${local.ktms_check_name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ktms_check" {
  name               = "tms-lambda-ktms-ml-ready-check"
  description        = "K-TMS ML-ready contract check (read-only on tables, writes its own run records)"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# research R6
data "aws_iam_policy_document" "ktms_check" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ktms_check.arn}:*"]
  }

  statement {
    sid       = "ListRawPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.ktms_ml_ready_table}/*",
        "${local.ktms_ml_ready_runs}/*",
        "${local.ktms_check_runs}/*",
      ]
    }
  }

  # 테이블 데이터·메타데이터(Athena가 읽음)와 ML-ready 실행 기록
  statement {
    sid     = "ReadMlReady"
    actions = ["s3:GetObject"]
    resources = [
      "${local.raw_arn}/${local.ktms_ml_ready_table}/*",
      "${local.raw_arn}/${local.ktms_ml_ready_runs}/*",
    ]
  }

  statement {
    sid       = "WriteOwnRunRecords"
    actions   = ["s3:PutObject"]
    resources = ["${local.raw_arn}/${local.ktms_check_runs}/*"]
  }

  statement {
    sid = "AthenaQuery"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
      "athena:GetWorkGroup",
    ]
    resources = ["arn:aws:athena:ap-northeast-2:${data.aws_caller_identity.current.account_id}:workgroup/${var.athena_workgroup}"]
  }

  statement {
    sid       = "AthenaResults"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${local.eda_arn}/athena-results/*"]
  }

  statement {
    sid       = "AthenaResultsBucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [local.eda_arn]
  }

  statement {
    sid     = "CatalogRead"
    actions = ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions"]
    resources = [
      "${local.ktms_glue_catalog}:catalog",
      "${local.ktms_glue_catalog}:database/tms_silver2",
      "${local.ktms_glue_catalog}:table/tms_silver2/ktms_ml_ready",
    ]
  }
}

resource "aws_iam_role_policy" "ktms_check" {
  name   = "tms-lambda-ktms-ml-ready-check"
  role   = aws_iam_role.ktms_check.id
  policy = data.aws_iam_policy_document.ktms_check.json
}

resource "aws_lambda_function" "ktms_check" {
  function_name    = local.ktms_check_name
  description      = "K-TMS ML-ready contract check after the daily rebuild (spec 010)"
  role             = aws_iam_role.ktms_check.arn
  runtime          = "python3.12"
  handler          = "lambda_ktms_ml_ready_check.handler"
  filename         = data.archive_file.ktms_check.output_path
  source_code_hash = data.archive_file.ktms_check.output_base64sha256
  layers           = [var.pandas_layer_arn, aws_lambda_layer_version.rules.arn]
  memory_size      = 2048
  timeout          = 300

  environment {
    variables = {
      BUCKET           = local.raw_bucket
      ATHENA_WORKGROUP = var.athena_workgroup
    }
  }

  depends_on = [aws_cloudwatch_log_group.ktms_check, aws_iam_role_policy.ktms_check]
}
