variable "guardrail_tier" {
  description = "가드레일 탐지 등급. STANDARD(한국어 포함 다국어, 교차 리전 프로필 필요) 또는 CLASSIC(영어 중심, 서울 안에서 처리)"
  type        = string
  default     = "STANDARD"

  validation {
    condition     = contains(["STANDARD", "CLASSIC"], var.guardrail_tier)
    error_message = "guardrail_tier는 STANDARD 또는 CLASSIC이다."
  }
}

variable "guardrail_profile_id" {
  description = "STANDARD 등급의 교차 리전 가드레일 프로필 ID. apply 전에 Bedrock 콘솔 가드레일 생성 화면의 교차 리전 항목에서 확인한다"
  type        = string
  default     = "apac.guardrail.v1:0"
}

variable "guardrail_enforce" {
  description = "실제로 차단할 정책 목록(쉼표). content, prompt_attack, grounding, words(비속어 단어, 018), 주제 이름(internal_info, tamper_request) 또는 topics(주제 전부) 중. none = 모두 감지만. 개인정보 가림은 항상 적용 (research R3·R3a)"
  type        = string
  default     = "content,prompt_attack,internal_info,words" # 018: 시험(v5) 뒤 차단. tamper_request·grounding은 감지만

  validation {
    condition = var.guardrail_enforce == "none" || alltrue([
      for v in split(",", var.guardrail_enforce) : contains(["content", "prompt_attack", "topics", "grounding", "words", "internal_info", "tamper_request"], trimspace(v))
    ])
    error_message = "guardrail_enforce는 none 또는 content, prompt_attack, topics, grounding, words, internal_info, tamper_request의 쉼표 목록이다."
  }
}

variable "agent_access_enabled" {
  description = "에이전트 서버 역할에 이 가드레일 검사 권한을 붙일지. 역할이 없는 환경에서는 false"
  type        = bool
  default     = true
}

variable "app_server_role_name" {
  description = "에이전트 서버 역할 이름(tms-app 스택이 만듦)"
  type        = string
  default     = "tms-app-server"
}

variable "guard_user_names" {
  description = "로컬 PC에서 본인 IAM 사용자로 이 가드레일을 시험할 사용자 이름 (비밀 아님). 그룹 tms-agent-guard-users"
  type        = list(string)
  default     = ["de-ai-05"]
}
