variable "raw_bucket_name" {
  description = "TW CEMS 원본 JSONL이 있는 원본 버킷 이름 (tms-collection 스택이 관리, 이 스택은 읽기만 한다)"
  type        = string
  default     = "smokestack-tms-raw-952900391026"
}

variable "eda_bucket_name" {
  description = "Athena EDA 전용 버킷 이름 (Parquet, Glue 스크립트·임시 파일, Athena 결과)"
  type        = string
  default     = "smokestack-tms-eda-952900391026"
}

variable "glue_worker_count" {
  description = "변환 Job의 G.1X 워커 수 (1워커 = 1 DPU)"
  type        = number
  default     = 10

  validation {
    condition     = var.glue_worker_count >= 2 && var.glue_worker_count <= 10
    error_message = "glue_worker_count는 2~10 사이여야 한다."
  }
}

variable "athena_bytes_scanned_cutoff" {
  description = "Athena 워크그룹의 쿼리당 최대 스캔 바이트 (기본 10GB)"
  type        = number
  default     = 10737418240
}
