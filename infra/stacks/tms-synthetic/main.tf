# 학습용 합성 K-TMS 데이터 AWS Bronze 적재. specs/a-platform/011-synthetic-train-s3-ingest
#
# EventBridge Scheduler(매 :10, :40 KST) → Lambda tms-synthetic-train → 원본 버킷 tms_synthetic_train/
# - 생성 규칙은 B의 k_tms_synthetic_train/synth_train을 수정 없이 zip에 넣는다. 진입점은 lambda_handler.py.
# - Kafka·Kinesis 없음(research R1). 에피소드는 seed로 매번 다시 계산(R2).
# - 실패: Scheduler 재시도+DLQ, Lambda 비동기 재시도 2회+실패 목적지(같은 SQS), DLQ 알람, 매일 06:00 점검(R5).
# - 이 스택은 tms_cleansys/·bronze/·silver2/에 권한이 없다(원칙 I, R6).

locals {
  name       = "tms-synthetic-train"
  root       = "tms_synthetic_train"
  source_dir = "${path.module}/../../../k_tms_synthetic_train"
  # research R3. plan.py는 PyYAML을 import하므로 넣지 않는다(설정은 daily.json).
  modules = [
    "synth_train/__init__.py",
    "synth_train/schedule.py",
    "synth_train/stats.py",
    "synth_train/daily.py",
    "synth_train/assemble.py",
    "synth_train/shapes.py",
    "synth_train/scenarios/__init__.py",
    "synth_train/scenarios/trajectory.py",
    "synth_train/episode.py", # scenarios/trajectory가 import
    "synth_train/pack.py",
    "synth_train/snapshot.py",
    "synth_train/writer.py",
    "synth_train/s3_sink.py",
    "synth_train/generate.py",
  ]
  raw_arn = data.aws_s3_bucket.raw.arn
}

data "aws_caller_identity" "current" {}

data "aws_s3_bucket" "raw" {
  bucket = var.raw_bucket_name
}

data "aws_sns_topic" "alerts" {
  name = var.alert_topic_name
}

# ---------------------------------------------------------------------------
# 코드
# ---------------------------------------------------------------------------

data "archive_file" "code" {
  type             = "zip"
  output_path      = "${local.source_dir}/build/${local.name}.zip"
  output_file_mode = "0666"

  source {
    content  = file("${local.source_dir}/lambda_handler.py")
    filename = "lambda_handler.py"
  }

  # B가 yaml을 고치면 다음 apply에 반영된다. PyYAML 없이 읽도록 JSON으로 바꿔 넣는다.
  source {
    content  = jsonencode(yamldecode(file("${local.source_dir}/config/daily.yaml")))
    filename = "config/daily.json"
  }

  dynamic "source" {
    for_each = local.modules
    content {
      content  = file("${local.source_dir}/${source.value}")
      filename = source.value
    }
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

# ---------------------------------------------------------------------------
# 실패 보관함 (일반 SQS, R5)
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-dlq"
  message_retention_seconds = 1209600 # 14일
  sqs_managed_sse_enabled   = true
}

# ---------------------------------------------------------------------------
# Lambda 역할 (R6)
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "tms-lambda-synthetic-train"
  description        = "Synthetic training data writer (tms_synthetic_train/ only)"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  # 확정 표지·태그 존재 확인(list_objects_v2)
  statement {
    sid       = "ListSyntheticPrefix"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.root}/*"]
    }
  }

  statement {
    sid     = "WriteSyntheticBronze"
    actions = ["s3:PutObject", "s3:GetObject"]
    resources = [
      "${local.raw_arn}/${local.root}/ingest_date=*",
      "${local.raw_arn}/${local.root}/_manifest/*",
    ]
  }

  statement {
    sid       = "ReadRefStats"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/${local.root}/_ref_stats/*"]
  }

  statement {
    sid       = "AlertMissingSlots"
    actions   = ["sns:Publish"]
    resources = [data.aws_sns_topic.alerts.arn]
  }

  statement {
    sid       = "FailureDestination"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "tms-lambda-synthetic-train"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_lambda_function" "this" {
  function_name    = local.name
  description      = "Synthetic K-TMS training data to tms_synthetic_train/ every 30 min (spec 011)"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "lambda_handler.handler"
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  layers           = [var.pandas_layer_arn]
  memory_size      = 1024
  timeout          = 900 # 백필(최대 31일)용. 정기 실행은 수십 초

  environment {
    variables = {
      BUCKET          = var.raw_bucket_name
      ALERT_TOPIC_ARN = data.aws_sns_topic.alerts.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.lambda]
}

resource "aws_lambda_function_event_invoke_config" "this" {
  function_name                = aws_lambda_function.this.function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600

  destination_config {
    on_failure {
      destination = aws_sqs_queue.dlq.arn
    }
  }
}

# ---------------------------------------------------------------------------
# 스케줄 (정기 :10·:40, 점검 06:00)
# ---------------------------------------------------------------------------

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
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "tms-scheduler-synthetic-train"
  description        = "Invokes tms-synthetic-train and sends undelivered events to its DLQ"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeLambda"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.this.arn]
  }

  statement {
    sid       = "DeadLetter"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "tms-scheduler-synthetic-train"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "regular" {
  name                         = local.name
  description                  = "Synthetic training snapshot every 30 min at :10/:40 KST, same as K-TMS folders (spec 011)"
  schedule_expression          = "cron(10,40 * * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"
  state                        = var.synthetic_schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.this.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ mode = "regular", scheduled_time = "<aws.scheduler.scheduled-time>" })

    retry_policy {
      maximum_retry_attempts       = 3
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}

resource "aws_scheduler_schedule" "check" {
  name                         = "${local.name}-check"
  description                  = "Checks yesterday's 48 synthetic slots have _SUCCESS, alerts if not (spec 011)"
  schedule_expression          = "cron(0 6 * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"
  state                        = var.synthetic_schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.this.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ mode = "check" })

    retry_policy {
      maximum_retry_attempts       = 3
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}

# ---------------------------------------------------------------------------
# 알람: 실패 보관함에 메시지가 생기면
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${local.name}-dlq-not-empty"
  alarm_description   = "tms-synthetic-train 실행이 재시도 뒤에도 실패해 DLQ에 남았다. 재처리: specs/a-platform/011-synthetic-train-s3-ingest/contracts/ingest-interface.md §3"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  alarm_actions = [data.aws_sns_topic.alerts.arn]
  ok_actions    = [data.aws_sns_topic.alerts.arn]
}
