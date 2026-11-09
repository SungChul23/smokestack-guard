variable "raw_bucket_name" {
  description = "원본 버킷 이름 (tms-collection 스택이 관리). 이 스택은 이름만 참조하고, bronze/tw_cems/ 읽기와 silver/tw_cems/ 쓰기에만 쓴다"
  type        = string
  default     = "smokestack-tms-raw-952900391026"
}

variable "glue_worker_count" {
  description = "Silver Job의 G.1X 워커 수 (1워커 = 1 DPU)"
  type        = number
  default     = 10

  validation {
    condition     = var.glue_worker_count >= 2 && var.glue_worker_count <= 10
    error_message = "glue_worker_count는 2~10 사이여야 한다."
  }
}

variable "glue_timeout_minutes" {
  description = "Silver Job 1회(한 달) 실행 제한 시간(분)"
  type        = number
  default     = 60
}
