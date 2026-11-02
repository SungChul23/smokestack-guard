variable "name" {
  description = "수집기 이름 (Lambda, 역할, 스케줄, 알람 이름에 사용)"
  type        = string
}

variable "source_dir" {
  description = "Lambda 코드가 있는 디렉터리 경로"
  type        = string
}

variable "handler" {
  description = "Lambda 핸들러 (파일.함수)"
  type        = string
}

variable "runtime" {
  description = "Lambda 런타임"
  type        = string
}

variable "timeout_seconds" {
  description = "Lambda 제한 시간(초)"
  type        = number
}

variable "memory_mb" {
  description = "Lambda 메모리(MB)"
  type        = number
}

variable "environment_variables" {
  description = "Lambda 환경 변수 (비밀값을 넣지 않는다)"
  type        = map(string)
}

variable "bucket_arn" {
  description = "수집 결과를 저장할 S3 버킷 ARN"
  type        = string
}

variable "api_key_parameter_name" {
  description = "API 키가 저장된 SSM 파라미터 이름 (값이 아니라 이름)"
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge Scheduler 스케줄 식"
  type        = string
}

variable "schedule_timezone" {
  description = "EventBridge Scheduler 스케줄 식의 시간대"
  type        = string
}

variable "schedule_input" {
  description = "Lambda에 전달할 입력 JSON 문자열"
  type        = string
}

variable "alarm_topic_arn" {
  description = "알람을 보낼 SNS 토픽 ARN"
  type        = string
}

variable "alarm_period_seconds" {
  description = "Errors 알람 평가 기간(초), 수집 주기보다 길게 잡는다"
  type        = number
}
