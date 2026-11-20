# 학습 스냅샷 알림 (specs/a-platform/015-synthetic-v2-snapshot-notice, US3)
#
# 매일 05:00 KST Scheduler → Lambda tms-training-snapshot-notice → SNS tms-training-snapshots → 이메일
# - 실행 기록(silver2/_runs/…)만 읽어 실측·합성의 계약 검사 통과 스냅샷(Silver·ML-ready)을 알린다. Athena 없음.
# - 수신 주소는 var.training_notice_emails(TF_VAR로만, 저장소에 쓰지 않음). 받는 사람이 구독 확인을 눌러야 한다.
# - VPC 밖, S3 읽기와 SNS 발행만.

locals {
  notice_name = "tms-training-snapshot-notice"
}

resource "aws_sns_topic" "training_snapshots" {
  name = "tms-training-snapshots"
}

resource "aws_sns_topic_subscription" "training_snapshots_email" {
  # 주소는 상태 파일에만 남는다(비밀은 아니지만 개인 정보라 저장소에는 쓰지 않는다)
  for_each  = nonsensitive(toset(var.training_notice_emails))
  topic_arn = aws_sns_topic.training_snapshots.arn
  protocol  = "email"
  endpoint  = each.value
}

data "archive_file" "training_notice" {
  type             = "zip"
  output_path      = "${local.ktms_services_dir}/build/training_snapshot_notice.zip"
  output_file_mode = "0666"

  source {
    content  = file("${local.ktms_services_dir}/lambda_training_snapshot_notice.py")
    filename = "lambda_training_snapshot_notice.py"
  }
}

resource "aws_cloudwatch_log_group" "training_notice" {
  name              = "/aws/lambda/${local.notice_name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_assume_notice" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "training_notice" {
  name               = "tms-lambda-training-snapshot-notice"
  description        = "Reads silver2/_runs records and emails training snapshot ids (spec 015)"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_notice.json
}

data "aws_iam_policy_document" "training_notice" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.training_notice.arn}:*"]
  }

  statement {
    sid       = "ListRunRecords"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["silver2/_runs/*"]
    }
  }

  statement {
    sid       = "ReadRunRecords"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/silver2/_runs/*"]
  }

  statement {
    sid       = "PublishNotice"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.training_snapshots.arn]
  }
}

resource "aws_iam_role_policy" "training_notice" {
  name   = "tms-lambda-training-snapshot-notice"
  role   = aws_iam_role.training_notice.id
  policy = data.aws_iam_policy_document.training_notice.json
}

resource "aws_lambda_function" "training_notice" {
  function_name    = local.notice_name
  description      = "Daily email of contract-checked training snapshots, real + synthetic (spec 015)"
  role             = aws_iam_role.training_notice.arn
  runtime          = "python3.12"
  handler          = "lambda_training_snapshot_notice.handler"
  filename         = data.archive_file.training_notice.output_path
  source_code_hash = data.archive_file.training_notice.output_base64sha256
  memory_size      = 256
  timeout          = 60

  environment {
    variables = {
      BUCKET    = local.raw_bucket
      TOPIC_ARN = aws_sns_topic.training_snapshots.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.training_notice, aws_iam_role_policy.training_notice]
}

resource "aws_iam_role" "training_notice_scheduler" {
  name               = "tms-scheduler-training-snapshot-notice"
  description        = "Invokes the training snapshot notice Lambda at 05:00 KST"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "training_notice_scheduler" {
  statement {
    sid       = "InvokeNotice"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.training_notice.arn]
  }
}

resource "aws_iam_role_policy" "training_notice_scheduler" {
  name   = "tms-scheduler-training-snapshot-notice"
  role   = aws_iam_role.training_notice_scheduler.id
  policy = data.aws_iam_policy_document.training_notice_scheduler.json
}

# 03:00 실측·03:30 합성 갱신과 계약 검사가 끝난 뒤
resource "aws_scheduler_schedule" "training_notice" {
  name                         = local.notice_name
  schedule_expression          = "cron(0 5 * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"
  state                        = var.training_notice_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.training_notice.arn
    role_arn = aws_iam_role.training_notice_scheduler.arn
    input    = jsonencode({})

    retry_policy {
      maximum_retry_attempts = 2
    }
  }
}
