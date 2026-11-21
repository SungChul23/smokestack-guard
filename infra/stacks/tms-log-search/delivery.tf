# 로그 전달: 구독 필터·EventBridge → 라우터 Lambda → Firehose 3개 → OpenSearch (research R3·R9)
#
# Firehose는 CloudWatch Logs 묶음을 OpenSearch에 직접 넣지 못한다. 라우터가 묶음을 풀어 로그 한 줄 = 레코드 하나로
# 나눠 보낸다. 실패분은 로그 버킷에 남는다. 수집 Lambda 코드·역할·스케줄은 건드리지 않는다(원칙 I).

locals {
  streams = {
    app      = "logs-app"
    pipeline = "logs-pipeline"
    activity = "activity"
  }
  services_dir    = "${path.module}/../../../services/log-search"
  subscribed      = var.opensearch_enabled ? toset(concat(var.app_log_groups, var.pipeline_log_groups)) : toset([])
  glue_subscribed = var.opensearch_enabled ? toset([var.glue_log_group]) : toset([])
}

# ---------------------------------------------------------------------------
# 실패분 버킷 (스위치와 상관없이 유지)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "logs" {
  bucket = var.logs_bucket_name
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    id     = "expire-28d"
    status = "Enabled"
    filter {}
    expiration {
      days = 28
    }
  }
}

# ---------------------------------------------------------------------------
# Firehose 3개
# ---------------------------------------------------------------------------

resource "aws_iam_role" "firehose" {
  count       = local.on
  name        = "tms-logs-firehose"
  description = "Firehose delivery to OpenSearch tms-logs and failed docs to the logs bucket (spec 014)"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "firehose.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "firehose" {
  count = local.on
  name  = "tms-logs-firehose"
  role  = aws_iam_role.firehose[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DescribeDomain"
        Effect   = "Allow"
        Action   = ["es:DescribeDomain", "es:DescribeDomains", "es:DescribeDomainConfig"]
        Resource = [local.domain_arn, "${local.domain_arn}/*"]
      },
      {
        Sid      = "WriteDomain"
        Effect   = "Allow"
        Action   = ["es:ESHttpPost", "es:ESHttpPut", "es:ESHttpGet"]
        Resource = [local.domain_arn, "${local.domain_arn}/*"]
      },
      {
        Sid      = "FailedDocs"
        Effect   = "Allow"
        Action   = ["s3:AbortMultipartUpload", "s3:GetBucketLocation", "s3:GetObject", "s3:ListBucket", "s3:ListBucketMultipartUploads", "s3:PutObject"]
        Resource = [aws_s3_bucket.logs.arn, "${aws_s3_bucket.logs.arn}/*"]
      },
    ]
  })
}

resource "aws_kinesis_firehose_delivery_stream" "logs" {
  for_each    = var.opensearch_enabled ? local.streams : {}
  name        = "tms-logs-${each.key}"
  destination = "opensearch"

  opensearch_configuration {
    domain_arn            = aws_opensearch_domain.logs[0].arn
    role_arn              = aws_iam_role.firehose[0].arn
    index_name            = each.value
    index_rotation_period = "OneDay"
    buffering_interval    = 60
    buffering_size        = 1
    retry_duration        = 300
    s3_backup_mode        = "FailedDocumentsOnly"

    s3_configuration {
      role_arn           = aws_iam_role.firehose[0].arn
      bucket_arn         = aws_s3_bucket.logs.arn
      prefix             = "failed/${each.key}/"
      compression_format = "GZIP"
    }
  }

  depends_on = [aws_iam_role_policy.firehose]
}

# ---------------------------------------------------------------------------
# 라우터 Lambda
# ---------------------------------------------------------------------------

data "archive_file" "router" {
  type             = "zip"
  output_path      = "${local.services_dir}/build/router.zip"
  output_file_mode = "0666"

  source {
    content  = file("${local.services_dir}/router.py")
    filename = "router.py"
  }
}

# 라우터 자기 로그는 구독하지 않는다(되먹임 방지)
resource "aws_cloudwatch_log_group" "router" {
  count             = local.on
  name              = "/aws/lambda/tms-logs-router"
  retention_in_days = 14
}

resource "aws_iam_role" "router" {
  count       = local.on
  name        = "tms-logs-router"
  description = "Splits CloudWatch Logs batches into one record per line and sends them to Firehose (spec 014)"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "router" {
  count = local.on
  name  = "tms-logs-router"
  role  = aws_iam_role.router[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.router[0].arn}:*"
      },
      {
        Sid      = "PutToFirehose"
        Effect   = "Allow"
        Action   = ["firehose:PutRecordBatch"]
        Resource = [for s in aws_kinesis_firehose_delivery_stream.logs : s.arn]
      },
    ]
  })
}

resource "aws_lambda_function" "router" {
  count            = local.on
  function_name    = "tms-logs-router"
  description      = "CloudWatch Logs and Step Functions events to Firehose, one record per line (spec 014)"
  role             = aws_iam_role.router[0].arn
  runtime          = "python3.12"
  handler          = "router.handler"
  filename         = data.archive_file.router.output_path
  source_code_hash = data.archive_file.router.output_base64sha256
  memory_size      = 256
  timeout          = 60

  environment {
    variables = {
      STREAM_APP      = aws_kinesis_firehose_delivery_stream.logs["app"].name
      STREAM_PIPELINE = aws_kinesis_firehose_delivery_stream.logs["pipeline"].name
      STREAM_ACTIVITY = aws_kinesis_firehose_delivery_stream.logs["activity"].name
    }
  }

  depends_on = [aws_cloudwatch_log_group.router, aws_iam_role_policy.router]
}

# ---------------------------------------------------------------------------
# 구독 필터 (로그 그룹 → 라우터)
# ---------------------------------------------------------------------------

resource "aws_lambda_permission" "logs" {
  for_each       = setunion(local.subscribed, local.glue_subscribed)
  statement_id   = "logs-${substr(sha1(each.value), 0, 12)}"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.router[0].function_name
  principal      = "logs.amazonaws.com"
  source_arn     = "arn:aws:logs:ap-northeast-2:${local.account_id}:log-group:${each.value}:*"
  source_account = local.account_id
}

resource "aws_cloudwatch_log_subscription_filter" "all" {
  for_each        = local.subscribed
  name            = "tms-logs-router"
  log_group_name  = each.value
  filter_pattern  = ""
  destination_arn = aws_lambda_function.router[0].arn
  depends_on      = [aws_lambda_permission.logs]
}

# Glue(Spark) 로그는 양이 많아 오류 줄만 (research R9)
resource "aws_cloudwatch_log_subscription_filter" "glue_errors" {
  for_each        = local.glue_subscribed
  name            = "tms-logs-router-errors"
  log_group_name  = each.value
  filter_pattern  = "?ERROR ?Exception ?Traceback"
  destination_arn = aws_lambda_function.router[0].arn
  depends_on      = [aws_lambda_permission.logs]
}

# ---------------------------------------------------------------------------
# Step Functions 실행 결과 (EventBridge → 라우터)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "sfn" {
  count       = local.on
  name        = "tms-logs-sfn-status"
  description = "Step Functions execution results to the log router (spec 014)"
  event_pattern = jsonencode({
    source        = ["aws.states"]
    "detail-type" = ["Step Functions Execution Status Change"]
    detail = {
      status          = ["SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"]
      stateMachineArn = [for m in var.state_machines : "arn:aws:states:ap-northeast-2:${local.account_id}:stateMachine:${m}"]
    }
  })
}

resource "aws_cloudwatch_event_target" "sfn" {
  count = local.on
  rule  = aws_cloudwatch_event_rule.sfn[0].name
  arn   = aws_lambda_function.router[0].arn
}

resource "aws_lambda_permission" "events" {
  count         = local.on
  statement_id  = "events-sfn-status"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.router[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sfn[0].arn
}
