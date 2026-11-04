variable "alert_email" {
  description = "수집 실패 알림을 받을 이메일 주소 (파일에 쓰지 않고 TF_VAR_alert_email 환경 변수로 전달)"
  type        = string
  sensitive   = true
}

variable "api_key_parameter_name" {
  description = "API 키가 저장된 SSM 파라미터 이름 (값은 콘솔에서 직접 등록)"
  type        = string
  default     = "/tms/collector/api-key"
}
