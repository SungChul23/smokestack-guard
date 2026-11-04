module "raw_archive" {
  source = "../../modules/raw-archive"

  bucket_name = "smokestack-tms-raw-952900391026"
}

resource "aws_sns_topic" "alerts" {
  name = "tms-collector-alerts"
}

resource "aws_sns_topic_subscription" "alert_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

module "collector" {
  source = "../../modules/scheduled-collector"

  name       = "tms-collector"
  source_dir = "${path.module}/../../../services/tms-collector"
  handler    = "handler.lambda_handler"
  runtime    = "python3.13"

  # API 호출 3회(회당 소켓 타임아웃 60초) + 백오프 7초 + S3 저장 시간
  timeout_seconds = 240
  memory_mb       = 256

  environment_variables = {
    BRONZE_BUCKET     = module.raw_archive.bucket_name
    API_KEY_PARAMETER = var.api_key_parameter_name
  }

  bucket_arn             = module.raw_archive.bucket_arn
  api_key_parameter_name = var.api_key_parameter_name

  # rate는 생성 시각 기준으로 돌므로, 매시 00분부터 10분 단위로 맞추기 위해 cron을 쓴다.
  schedule_expression = "cron(0/10 * * * ? *)"
  schedule_timezone   = "Asia/Seoul"

  # jsonencode는 <, >를 <, >로 바꿔 컨텍스트 속성이 치환되지 않으므로 문자열로 쓴다.
  # Lambda 자동 재시도도 같은 시각을 받아 같은 경로에 저장된다.
  schedule_input = "{\"time\": \"<aws.scheduler.scheduled-time>\"}"

  alarm_topic_arn      = aws_sns_topic.alerts.arn
  alarm_period_seconds = 900
}
