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
  description = "수집 결과를 읽고 쓸 S3 버킷 ARN. null이면 기본 S3 권한(버킷 전체 GetObject/PutObject)을 만들지 않는다"
  type        = string
  default     = null
}

variable "api_key_parameter_name" {
  description = "API 키가 저장된 SSM 파라미터 이름 (값이 아니라 이름). null이면 SSM·KMS 권한을 만들지 않는다"
  type        = string
  default     = null
}

variable "additional_policy_statements" {
  description = "실행 역할에 추가할 IAM 정책 문장 (기본 문장 뒤에 붙는다)"
  type = list(object({
    sid       = string
    actions   = list(string)
    resources = list(string)
    conditions = optional(list(object({
      test     = string
      variable = string
      values   = list(string)
    })), [])
  }))
  default = []
}

variable "maximum_retry_attempts" {
  description = "비동기 호출 실패 시 Lambda 자동 재시도 횟수(0–2). null이면 AWS 기본값(2)을 쓰고 별도 설정을 만들지 않는다"
  type        = number
  default     = null

  validation {
    condition     = var.maximum_retry_attempts == null || try(var.maximum_retry_attempts >= 0 && var.maximum_retry_attempts <= 2, false)
    error_message = "maximum_retry_attempts는 null 또는 0–2여야 한다."
  }
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
  description = "Errors 알람 평가 기간(초), 실행 주기보다 길게 잡는다"
  type        = number
}

variable "alarm_treat_missing_data" {
  description = "Errors 지표가 없을 때 처리. 자주 도는 함수는 breaching(호출 중단도 경보), 드물게 도는 함수는 notBreaching"
  type        = string
  default     = "breaching"

  validation {
    condition     = contains(["breaching", "notBreaching", "ignore", "missing"], var.alarm_treat_missing_data)
    error_message = "alarm_treat_missing_data는 breaching, notBreaching, ignore, missing 중 하나여야 한다."
  }
}

variable "alarm_description" {
  description = "알람 설명. null이면 \"<name> 실행 실패 또는 호출 중단\""
  type        = string
  default     = null
}
