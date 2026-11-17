variable "domain_name" {
  description = "서비스 도메인 (서버 주소 api.<도메인>, CORS 출처 https://<도메인>)"
  type        = string
  default     = "smokestack-guard.store"
}

variable "alb_enabled" {
  description = "ALB와 api. 레코드를 켠다"
  type        = bool
  default     = false
}

variable "api_desired" {
  description = "API 서버 대수 0(꺼 둠)·1(개발)·2(시연)"
  type        = number
  default     = 0

  validation {
    condition     = contains([0, 1, 2], var.api_desired)
    error_message = "api_desired는 0, 1, 2 중 하나여야 한다."
  }
}

variable "agent_desired" {
  description = "에이전트 서버 대수 0(꺼 둠)·1(개발)·2(시연)"
  type        = number
  default     = 0

  validation {
    condition     = contains([0, 1, 2], var.agent_desired)
    error_message = "agent_desired는 0, 1, 2 중 하나여야 한다."
  }
}

variable "api_instance_type" {
  description = "API 서버 인스턴스 유형 (x86)"
  type        = string
  default     = "t3.small"
}

variable "agent_instance_type" {
  description = "에이전트 서버 인스턴스 유형 (x86, 메모리가 부족하면 t3.medium)"
  type        = string
  default     = "t3.small"
}

variable "web_bucket_name" {
  description = "화면 버킷 이름 (tms-serving이 만든 것, 배포 역할 권한 대상)"
  type        = string
  default     = "smokestack-tms-web-952900391026"
}

variable "github_repository" {
  description = "배포 역할을 받을 수 있는 GitHub 저장소 (owner/name). main 브랜치만"
  type        = string
  default     = "SungChul23/smokestack-guard"
}
