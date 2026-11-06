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

# 전날(KST) 슬롯 누락률 리포트. 수집기와 같은 모듈을 쓰되 권한·재시도·알람을 다르게 준다.
# specs/a-platform/002-missing-rate-report
module "missing_rate" {
  source = "../../modules/scheduled-collector"

  name       = "tms-missing-rate"
  source_dir = "${path.module}/../../../services/tms-missing-rate"
  handler    = "handler.lambda_handler"
  runtime    = "python3.13"

  # UTC 이틀치 원본(정상 시 약 96개 폴더)의 메타·원문을 읽고 gzip 해제·JSON 파싱한다.
  timeout_seconds = 180
  memory_mb       = 512

  environment_variables = {
    BRONZE_BUCKET   = module.raw_archive.bucket_name
    ALERT_TOPIC_ARN = aws_sns_topic.alerts.arn
  }

  # API 키와 버킷 전체 읽기·쓰기 권한은 주지 않는다 (api_key_parameter_name, bucket_arn 생략).
  # 원본은 읽기만, 쓰기는 리포트 경로만 허용해 코드 실수로도 원본을 바꿀 수 없게 한다.
  additional_policy_statements = [
    {
      sid       = "ListRawPrefix"
      actions   = ["s3:ListBucket"]
      resources = [module.raw_archive.bucket_arn]
      conditions = [{
        test     = "StringLike"
        variable = "s3:prefix"
        values   = ["tms_cleansys/*"]
      }]
    },
    {
      sid       = "ReadRawObjects"
      actions   = ["s3:GetObject"]
      resources = ["${module.raw_archive.bucket_arn}/tms_cleansys/*"]
    },
    {
      sid       = "WriteMissingRateReports"
      actions   = ["s3:PutObject"]
      resources = ["${module.raw_archive.bucket_arn}/reports/missing_rate/*"]
    },
    {
      sid       = "PublishAlerts"
      actions   = ["sns:Publish"]
      resources = [aws_sns_topic.alerts.arn]
    },
  ]

  # 재시도해도 결과가 같고, 복구는 수동 백필로 한다.
  maximum_retry_attempts = 0

  # API 반영 지연(약 2시간) 뒤, 업무 시작 시각에 전날을 계산한다.
  schedule_expression = "cron(0 9 * * ? *)"
  schedule_timezone   = "Asia/Seoul"
  schedule_input      = "{}"

  # 하루 한 번 도는 함수라 값 없음은 정상으로 보고, 하루 구간의 실패만 알린다.
  # 누락 자체는 함수가 SNS로 직접 알린다.
  alarm_topic_arn          = aws_sns_topic.alerts.arn
  alarm_period_seconds     = 86400
  alarm_treat_missing_data = "notBreaching"
  alarm_description        = "tms-missing-rate 계산 실패"
}
