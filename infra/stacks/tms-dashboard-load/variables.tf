variable "raw_bucket_name" {
  description = "원본 버킷 (tms_cleansys/ 읽기만)"
  type        = string
  default     = "smokestack-tms-raw-952900391026"
}

variable "pandas_layer_arn" {
  description = "AWS SDK for pandas 관리형 레이어(Python 3.12) ARN. 010 계약 검사 Lambda와 같은 값"
  type        = string
  default     = "arn:aws:lambda:ap-northeast-2:336392948345:layer:AWSSDKPandas-Python312:18"
}

variable "rules_layer_name" {
  description = "C의 규칙 패키지(src/smokestack_guard) 레이어 이름. tms-silver 스택이 만든 최신 버전을 쓴다"
  type        = string
  default     = "tms-smokestack-guard-rules"
}

variable "alert_topic_name" {
  description = "실패·새 사업장 이름을 알릴 운영 SNS 토픽"
  type        = string
  default     = "tms-collector-alerts"
}

variable "db_instance_identifier" {
  description = "적재 대상 RDS 인스턴스 (009 tms-database)"
  type        = string
  default     = "tms-db"
}

variable "load_schedule_enabled" {
  description = "30분 적재(:15·:45)와 매일 요약(03:20) 스케줄을 켤지. migrate·load-ref·backfill(10/30~11/19)과 Silver 비교를 마치고 2026-11-19에 켰다 (012 quickstart §7). 잠시 멈추려면 TF_VAR_load_schedule_enabled=false"
  type        = bool
  default     = true
}

variable "recent_hours" {
  description = "30분 적재가 읽는 최근 수집 시각 범위(시간). 실행이 몇 번 빠져도 다음 실행이 메우도록 겹치게 둔다"
  type        = number
  default     = 4
}
