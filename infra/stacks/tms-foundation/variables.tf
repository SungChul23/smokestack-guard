variable "domain_name" {
  description = "서비스 도메인 (카페24에서 구매, Route 53으로 NS 위임)"
  type        = string
  default     = "smokestack-guard.store"
}

variable "alert_email" {
  description = "비용 알림을 받을 이메일 주소 (파일에 쓰지 않고 TF_VAR_alert_email 환경 변수로 전달)"
  type        = string
  sensitive   = true
}

variable "monthly_budget_usd" {
  description = "월 비용 예산(USD). 알림은 실제 25%·50%·75%, 예상 100%"
  type        = number
  default     = 200
}
