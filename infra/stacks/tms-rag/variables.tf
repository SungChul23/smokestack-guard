# RAG 문서 지식 기반 (spec 016). 적용 순서는 specs/a-platform/016-rag-knowledge-base/quickstart.md

variable "rag_kb_enabled" {
  description = "지식 기반·데이터 소스를 만든다. 인덱스 rag-docs와 FGAC 매핑(setup_opensearch.py)이 먼저 있어야 한다(도메인을 새로 만들 땐 처음 apply만 false). 끄면 지식 기반이 지워지고 다시 켜면 전체 재동기화(임베딩만, 1센트 안팎)가 필요하다. 2026-11-23 생성 뒤 기본 true"
  type        = bool
  default     = true
}

variable "agent_retrieve_enabled" {
  description = "에이전트 서버 역할(tms-app-server)에 이 지식 기반 Retrieve 권한을 주고 ID를 SSM(/tms/app/config/rag-knowledge-base-id)에 둔다. rag_kb_enabled가 true일 때만. tms-app 스택(서버 역할)이 먼저 있어야 한다. 2026-11-24 기본 true"
  type        = bool
  default     = true
}

variable "embedding_model_id" {
  description = "임베딩 모델 ID. 지식 기반을 만든 뒤 바꾸면 인덱스·지식 기반을 다시 만들어야 한다"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embedding_dimensions" {
  description = "임베딩 차원. 인덱스 rag-docs의 knn_vector dimension과 같아야 한다"
  type        = number
  default     = 1024
}

variable "answer_profile_id" {
  description = "RetrieveAndGenerate 답변 모델의 추론 프로필 ID(로컬 시험 --answer 기본값, 에이전트 권한). 비교용 Sonnet 4.6은 ask.py --model sonnet"
  type        = string
  default     = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "opensearch_domain_name" {
  description = "벡터 저장소로 쓰는 OpenSearch 도메인(014 tms-log-search 스택)"
  type        = string
  default     = "tms-logs"
}

variable "index_name" {
  description = "지식 기반이 쓰는 OpenSearch 인덱스. services/log-search/opensearch/indices/와 같은 이름"
  type        = string
  default     = "rag-docs"
}
