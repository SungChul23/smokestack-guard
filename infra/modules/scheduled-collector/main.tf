terraform {
  required_version = "~> 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# 파라미터 값이 상태 파일에 남지 않도록 SSM 파라미터 자체는 조회하지 않는다.
# IAM의 KMS 권한은 별칭이 아니라 키 ARN이 필요하다.
# API 키를 쓰지 않는 함수(api_key_parameter_name = null)는 조회하지 않는다.
data "aws_kms_alias" "ssm" {
  count = var.api_key_parameter_name == null ? 0 : 1

  name = "alias/aws/ssm"
}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  region        = data.aws_region.current.region
  parameter_arn = var.api_key_parameter_name == null ? null : "arn:aws:ssm:${local.region}:${local.account_id}:parameter/${trimprefix(var.api_key_parameter_name, "/")}"
}

data "archive_file" "code" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${var.source_dir}/${var.name}.zip"
  # 테스트·백필 명령·로컬 환경 파일은 함수에 필요 없다(specs/a-platform/007-ktms-bronze-success-marker research R5).
  excludes = [
    "${var.name}.zip", "__pycache__/**", "README.md",
    "tests/**", "pyproject.toml", "uv.lock", "backfill_markers.py", ".pytest_cache/**", ".venv/**",
  ]
  output_file_mode = "0666"
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = 14
}

# Lambda 실행 역할
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }

  # 아래 문장의 순서와 sid를 바꾸면 기존 함수의 정책이 바뀐다.
  dynamic "statement" {
    for_each = var.bucket_arn == null ? [] : [var.bucket_arn]

    content {
      sid       = "ReadWriteRawObjects"
      actions   = ["s3:GetObject", "s3:PutObject"]
      resources = ["${statement.value}/*"]
    }
  }

  dynamic "statement" {
    for_each = local.parameter_arn == null ? [] : [local.parameter_arn]

    content {
      sid       = "ReadApiKey"
      actions   = ["ssm:GetParameter"]
      resources = [statement.value]
    }
  }

  dynamic "statement" {
    for_each = data.aws_kms_alias.ssm

    content {
      sid       = "DecryptApiKey"
      actions   = ["kms:Decrypt"]
      resources = [statement.value.target_key_arn]
    }
  }

  dynamic "statement" {
    for_each = var.additional_policy_statements

    content {
      sid       = statement.value.sid
      actions   = statement.value.actions
      resources = statement.value.resources

      dynamic "condition" {
        for_each = statement.value.conditions

        content {
          test     = condition.value.test
          variable = condition.value.variable
          values   = condition.value.values
        }
      }
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_lambda_function" "this" {
  function_name = var.name
  role          = aws_iam_role.lambda.arn
  runtime       = var.runtime
  handler       = var.handler
  timeout       = var.timeout_seconds
  memory_size   = var.memory_mb

  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256

  environment {
    variables = var.environment_variables
  }

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.lambda,
  ]
}

# 재시도해도 결과가 같은 함수는 자동 재시도를 끈다. null이면 AWS 기본값(2회)을 쓴다.
resource "aws_lambda_function_event_invoke_config" "this" {
  count = var.maximum_retry_attempts == null ? 0 : 1

  function_name          = aws_lambda_function.this.function_name
  maximum_retry_attempts = var.maximum_retry_attempts
}

# 스케줄러 전용 호출 역할
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeCollector"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.this.arn]
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.name}-scheduler"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "this" {
  name                         = var.name
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.this.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = var.schedule_input
  }
}

# breaching(기본): 호출이 멈추면 Errors 지표가 비므로, 값 없음도 경보로 본다.
# 기간을 실행 주기보다 길게 잡아 정상 실행 중에 빈 구간이 생기지 않게 한다.
# 하루 한 번 도는 함수처럼 대부분의 구간에 값이 없는 함수는 notBreaching으로 실패만 본다.
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.name}-errors"
  alarm_description   = coalesce(var.alarm_description, "${var.name} 실행 실패 또는 호출 중단")
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = var.alarm_period_seconds
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = var.alarm_treat_missing_data

  dimensions = {
    FunctionName = aws_lambda_function.this.function_name
  }

  alarm_actions = [var.alarm_topic_arn]
  ok_actions    = [var.alarm_topic_arn]
}
