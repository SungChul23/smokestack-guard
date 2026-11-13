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

variable "silver2_ml_ready_reference" {
  description = "ML-ready2 compare 모드의 정답지(C가 bronze2로 만든 pandas 결과) S3 경로. Terraform 밖 버킷이며 읽기만 한다"
  type        = string
  default     = "s3://smokestack-cems-local-eda-952900391026/tw_cems_ml_ready_fixed/part.parquet"
}

# ---------------------------------------------------------------------------
# K-TMS Silver·ML-ready (008)
# ---------------------------------------------------------------------------

variable "ktms_schedule_enabled" {
  description = "K-TMS 매일 03:00 KST 실행 스케줄을 켤지. 처음 전체 생성(10-30 ~ 11-12)과 PR #45 수치 비교를 마치고 2026-11-13에 켰다 (008 quickstart §7). 잠시 멈추려면 TF_VAR_ktms_schedule_enabled=false"
  type        = bool
  default     = true
}

variable "ktms_worker_type" {
  description = "K-TMS Silver·ML-ready Job의 워커 종류. 계산은 driver 한 대의 pandas가 하므로 수보다 크기(메모리)가 중요하다. G.2X = driver 32GB, DPU당 2배 비용. 백필에서 메모리가 부족할 때만 TF_VAR_ktms_worker_type=G.2X로 잠깐 올린다"
  type        = string
  default     = "G.1X"

  validation {
    condition     = contains(["G.1X", "G.2X"], var.ktms_worker_type)
    error_message = "ktms_worker_type은 G.1X 또는 G.2X여야 한다."
  }
}

variable "ktms_worker_count" {
  description = "K-TMS Silver·ML-ready Job의 워커 수. 계산은 driver의 pandas가 하므로 늘려도 빨라지지 않는다. Glue 최소값 2"
  type        = number
  default     = 2

  validation {
    condition     = var.ktms_worker_count >= 2 && var.ktms_worker_count <= 4
    error_message = "ktms_worker_count는 2~4 사이여야 한다."
  }
}
