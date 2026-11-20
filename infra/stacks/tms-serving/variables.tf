variable "domain_name" {
  description = "서비스 도메인. 화면은 루트와 www, 서버는 api."
  type        = string
  default     = "smokestack-guard.store"
}

variable "web_bucket_name" {
  description = "화면(React 빌드) 버킷 이름"
  type        = string
  default     = "smokestack-tms-web-952900391026"
}

variable "cognito_domain_prefix" {
  description = "Cognito 관리형 로그인 접두사 도메인 (<접두사>.auth.ap-northeast-2.amazoncognito.com)"
  type        = string
  default     = "smokestack-guard"
}

variable "auth_redirect_urls" {
  description = "로그인·로그아웃 뒤 돌아갈 주소 (운영 화면 + 로컬 개발)"
  type        = list(string)
  default     = ["https://smokestack-guard.store/", "http://localhost:5173/"]
}

variable "login_providers" {
  description = "앱 클라이언트가 허용하는 로그인 공급자 이름. Google은 사람이 Cognito 콘솔에서 등록한다(시크릿은 Terraform에 넣지 않음, 013 R1). 등록 전이면 apply가 실패한다"
  type        = list(string)
  default     = ["Google"]
}
