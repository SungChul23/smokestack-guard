variable "domain_name" {
  description = "서비스 도메인 (배스천 이름 bastion.<도메인>)"
  type        = string
  default     = "smokestack-guard.store"
}

variable "rds_enabled" {
  description = "DB와 배스천을 함께 켠다. false면 둘 다 지운다(DB는 마지막 스냅샷을 남김)"
  type        = bool
  default     = false
}

variable "db_multi_az" {
  description = "DB Multi-AZ (개발 false, 시연 true)"
  type        = bool
  default     = false
}

variable "db_instance_class" {
  description = "RDS 인스턴스 클래스"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_engine_version" {
  description = "PostgreSQL 주 버전 (pgvector 지원)"
  type        = string
  default     = "16"
}

variable "db_restore_snapshot_id" {
  description = "켤 때 되살릴 스냅샷 ID. 빈 값이면 새 DB"
  type        = string
  default     = ""
}

variable "bastion_key_name" {
  description = "배스천 공용 SSH 키 쌍 이름 (EC2 콘솔에서 A가 만든다. 개인 키는 저장소·상태에 두지 않음)"
  type        = string
  default     = "tms-bastion"
}

variable "bastion_instance_type" {
  description = "배스천 인스턴스 유형"
  type        = string
  default     = "t3.micro"
}

variable "db_user_names" {
  description = "DB 관리자 비밀번호를 읽을 IAM 사용자 이름 (비밀 아님)"
  type        = list(string)
  default     = ["de-ai-05", "de-ai-08", "de-ai-11", "de-ai-14", "de-ai-22", "tms_mentor"]
}
