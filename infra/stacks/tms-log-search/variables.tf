# 서비스 로그 수집·분석 (specs/a-platform/014-log-opensearch)

variable "opensearch_enabled" {
  description = "OpenSearch 도메인·Firehose·라우터·구독 필터를 만들지. 시연이 끝나면 false로 지운다(원본 로그는 CloudWatch, 실패분은 S3에 남음). 기본 true(2026-11 약 28일 상시)"
  type        = bool
  default     = true
}

variable "engine_version" {
  description = "OpenSearch 엔진 버전 (2026-11-21 서울 최신 2.x)"
  type        = string
  default     = "OpenSearch_2.19"
}

variable "instance_type" {
  description = "도메인 인스턴스. 힙 사용률(JVMMemoryPressure)이 자주 80%를 넘으면 t3.medium.search로 올린다(데이터 유지)"
  type        = string
  default     = "t3.small.search"
}

variable "volume_gb" {
  description = "도메인 디스크(gp3, GB). 로그는 하루 수 MB라 10GB로 충분 (research R7)"
  type        = number
  default     = 10
}

variable "app_log_groups" {
  description = "서버 로그 그룹(라우터가 activity와 그 밖으로 나눔). tms-app 스택이 만든다"
  type        = list(string)
  default     = ["/tms/app/api", "/tms/app/agent"]
}

variable "pipeline_log_groups" {
  description = "데이터 파이프라인 Lambda 로그 그룹. 각 스택이 만든다"
  type        = list(string)
  default = [
    "/aws/lambda/tms-collector",
    "/aws/lambda/tms-missing-rate",
    "/aws/lambda/tms-dashboard-load",
    "/aws/lambda/tms-synthetic-train",
    "/aws/lambda/tms-ktms-ml-ready-check",
    "/aws/lambda/tms-training-snapshot-notice",
  ]
}

variable "glue_log_group" {
  description = "Glue 잡 로그 그룹(오류 줄만 받음)"
  type        = string
  default     = "/aws-glue/tms-silver"
}

variable "state_machines" {
  description = "실행 결과를 모을 상태 머신 이름"
  type        = list(string)
  default     = ["tms-silver2-ktms", "tms-dashboard-load"]
}

variable "alert_topic_name" {
  description = "오류 몰림 알림을 보낼 운영 SNS 토픽 (tms-collection 스택)"
  type        = string
  default     = "tms-collector-alerts"
}

variable "logs_bucket_name" {
  description = "Firehose 전달 실패분 버킷. 원본 버킷과 따로 두고 28일 뒤 지운다(버려도 되는 운영 데이터)"
  type        = string
  default     = "smokestack-tms-logs-952900391026"
}

variable "nori_package_id" {
  description = "한국어 형태소 분석기 analysis-nori 선택 플러그인 패키지 ID(엔진 버전마다 다름, 2.19 = G5688189). RAG 인덱스 rag-docs(016)의 본문 분석기. 빈 문자열이면 연결하지 않는다. 엔진 버전을 올리면 그 버전의 ID로 바꾼다"
  type        = string
  default     = "G5688189"
}
