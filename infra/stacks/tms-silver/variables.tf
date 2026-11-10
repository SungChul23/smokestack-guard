variable "raw_bucket_name" {
  description = "원본 버킷 이름 (tms-collection 스택이 관리). 이 스택은 이름만 참조하고, bronze/tw_cems/·bronze2/tw_cems/ 읽기와 silver/·silver2/ 아래 TW CEMS 테이블 쓰기에만 쓴다"
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

variable "ml_ready_worker_count" {
  description = "ML-ready Job의 G.1X 워커 수 (1워커 = 1 DPU)"
  type        = number
  default     = 10

  validation {
    condition     = var.ml_ready_worker_count >= 2 && var.ml_ready_worker_count <= 10
    error_message = "ml_ready_worker_count는 2~10 사이여야 한다."
  }
}

variable "ml_ready_reference" {
  description = "ML-ready compare 모드의 정답지(C의 pandas 결과) S3 경로. Terraform 밖 버킷이며 읽기만 한다"
  type        = string
  default     = "s3://smokestack-cems-local-eda-952900391026/ml_ready/part.parquet"
}
