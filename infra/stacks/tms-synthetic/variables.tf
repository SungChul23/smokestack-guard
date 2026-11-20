variable "raw_bucket_name" {
  description = "원본 버킷 이름 (tms-collection 스택이 관리). 이 스택은 tms_synthetic_train_v2/ 아래에만 쓴다(v1 tms_synthetic_train/은 보존만)"
  type        = string
  default     = "smokestack-tms-raw-952900391026"
}

variable "alert_topic_name" {
  description = "운영 알림 SNS 토픽 이름 (tms-collection 스택이 관리, 이메일 구독)"
  type        = string
  default     = "tms-collector-alerts"
}

variable "pandas_layer_arn" {
  description = "AWS SDK for pandas 관리형 레이어(Python 3.12) ARN. numpy·pandas를 쓴다 (010과 같은 값)"
  type        = string
  default     = "arn:aws:lambda:ap-northeast-2:336392948345:layer:AWSSDKPandas-Python312:18"
}

variable "synthetic_schedule_enabled" {
  description = "30분 정기 적재(매 :10, :40 KST)와 매일 06:00 점검 스케줄을 켤지. 슬롯 하나·바이트 비교를 확인하고 2026-11-17에 켰다 (011 quickstart §6). 잠시 멈추려면 TF_VAR_synthetic_schedule_enabled=false"
  type        = bool
  default     = true
}
