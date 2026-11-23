# RAG 문서 지식 기반 (spec 016). 적용 순서는 specs/a-platform/016-rag-knowledge-base/quickstart.md

variable "rag_kb_enabled" {
  description = "지식 기반·데이터 소스를 만든다. 인덱스 rag-docs와 FGAC 매핑(setup_opensearch.py)이 먼저 있어야 한다. 처음 apply는 false"
  type        = bool
  default     = false
}

variable "agent_retrieve_enabled" {
  description = "에이전트 서버 역할(tms-app-server)에 이 지식 기반 Retrieve 권한을 주고 ID를 SSM에 둔다. rag_kb_enabled가 true일 때만"
  type        = bool
  default     = false
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

variable "parser_profile_id" {
  description = "PDF를 읽는 파서 모델의 추론 프로필 ID(서울은 Claude를 추론 프로필로만 부른다). 지식 기반 파싱 허용 목록에 없다는 오류가 나면 허용 목록의 다른 Claude로 바꾼다. Haiku 5.5(약 1/10 가격)는 사례가 쌓인 뒤 비교"
  type        = string
  default     = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "answer_profile_id" {
  description = "RetrieveAndGenerate 답변 모델의 추론 프로필 ID(로컬 시험 --answer 기본값, 에이전트 권한). 비교용 Sonnet은 ask.py --model sonnet"
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
