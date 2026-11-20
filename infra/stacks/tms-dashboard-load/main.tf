# 대시보드 관측 적재 (spec 012). VPC 앱 서브넷의 Lambda가 S3 게이트웨이 엔드포인트로 원본을 읽고
# IAM 인증으로 RDS에 쓴다. NAT·인터페이스 엔드포인트는 쓰지 않는다 (research R1·R4).
# 상태 머신·스케줄은 state_machine.tf.

data "aws_caller_identity" "current" {}

data "aws_s3_bucket" "raw" {
  bucket = var.raw_bucket_name
}

data "aws_sns_topic" "alerts" {
  name = var.alert_topic_name
}

data "aws_vpc" "main" {
  tags = { Name = "tms-vpc" }
}

data "aws_subnet" "app" {
  for_each = toset(["app-a", "app-c"])

  vpc_id = data.aws_vpc.main.id
  tags   = { Name = "tms-${each.key}" }
}

data "aws_security_group" "loader" {
  vpc_id = data.aws_vpc.main.id
  name   = "tms-loader"
}

# C의 규칙 패키지 레이어(010과 같은 zip). tms-silver 스택이 올린 최신 버전.
data "aws_lambda_layer_version" "rules" {
  layer_name = var.rules_layer_name
}

locals {
  name        = "tms-dashboard-load"
  service_dir = "${path.module}/../../../services/dashboard-load"
  silver_dir  = "${path.module}/../../../services/tms-silver"
  account_id  = data.aws_caller_identity.current.account_id
  region      = "ap-northeast-2"
}

# ── 코드 ──
# 진입점 + 적재 모듈 + 008 범위 함수 + RDS 공용 CA 번들
data "archive_file" "code" {
  type             = "zip"
  output_path      = "${local.service_dir}/build/dashboard_load.zip"
  output_file_mode = "0666"

  source {
    content  = file("${local.service_dir}/lambda_handler.py")
    filename = "lambda_handler.py"
  }
  source {
    content  = file("${local.service_dir}/load.py")
    filename = "load.py"
  }
  source {
    content  = file("${local.service_dir}/db.py")
    filename = "db.py"
  }
  source {
    content  = file("${local.silver_dir}/ktms_pipeline.py")
    filename = "ktms_pipeline.py"
  }
  source {
    content  = file("${local.service_dir}/certs/global-bundle.pem")
    filename = "certs/global-bundle.pem"
  }
}

# pg8000 (순수 파이썬). services/dashboard-load/build_layer.sh로 먼저 만든다 (research R5).
resource "aws_lambda_layer_version" "pg8000" {
  layer_name          = "tms-pg8000"
  description         = "pg8000 PostgreSQL driver (pure Python)"
  filename            = "${local.service_dir}/build/pg8000_layer.zip"
  source_code_hash    = filebase64sha256("${local.service_dir}/build/pg8000_layer.zip")
  compatible_runtimes = ["python3.12"]
}

# ── 역할 (plan IAM 표) ──
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
  name               = "tms-lambda-dashboard-load"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "ListRawKtms"
    actions   = ["s3:ListBucket"]
    resources = [data.aws_s3_bucket.raw.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["tms_cleansys/*"]
    }
  }
  statement {
    sid       = "ReadRawKtms"
    actions   = ["s3:GetObject"]
    resources = ["${data.aws_s3_bucket.raw.arn}/tms_cleansys/*"]
  }
  statement {
    sid     = "ConnectAsLoader"
    actions = ["rds-db:connect"]
    # 스냅샷에서 다시 만들면 리소스 ID가 바뀌므로 인스턴스 부분은 *로 두고 계정 이름으로 좁힌다 (R4)
    resources = ["arn:aws:rds-db:${local.region}:${local.account_id}:dbuser:*/tms_loader"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "tms-lambda-dashboard-load"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# ── Lambda ──
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "load" {
  function_name    = local.name
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "lambda_handler.handler"
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  memory_size      = 3072 # 다시 채우기(day)는 원본 3일치를 pandas로 변환한다
  timeout          = 900
  layers = [
    var.pandas_layer_arn,
    data.aws_lambda_layer_version.rules.arn,
    aws_lambda_layer_version.pg8000.arn,
  ]

  vpc_config {
    subnet_ids         = [for s in data.aws_subnet.app : s.id]
    security_group_ids = [data.aws_security_group.loader.id]
  }

  environment {
    variables = {
      BUCKET       = var.raw_bucket_name
      DB_USER      = "tms_loader"
      RECENT_HOURS = tostring(var.recent_hours)
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy_attachment.lambda_vpc]
}
