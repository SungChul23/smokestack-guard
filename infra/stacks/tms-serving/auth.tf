# 로그인: 사용자 풀 + 화면용 공개 앱 클라이언트 (009 research R8)
# 013: 로그인은 Google만. Google 공급자(클라이언트 ID·시크릿)는 사람이 콘솔에서 등록하고 여기서는 이름만 참조한다
#      (Terraform으로 만들면 시크릿이 상태 파일에 평문으로 남는다). 서비스 자격은 그룹 members(초대 코드 통과).
# "관리자만 계정 생성"은 자체 가입만 막고 Google 첫 로그인은 막지 않는다(013 research R2).

resource "aws_cognito_user_pool" "main" {
  name = "tms-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"
  deletion_protection      = "ACTIVE"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.main.id
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "tms-web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = var.login_providers
  callback_urls                        = var.auth_redirect_urls
  logout_urls                          = var.auth_redirect_urls
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH"] # 비밀번호 로그인 흐름 없음 (013)
  prevent_user_existence_errors        = "ENABLED"
}

# 초대 코드를 통과한 회원. 서버가 Access 토큰의 cognito:groups로 확인한다 (013 research R3)
resource "aws_cognito_user_group" "members" {
  name         = "members"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "초대 코드 통과. 대시보드 API·에이전트 사용 자격 (013)"
}

resource "aws_ssm_parameter" "auth" {
  for_each = {
    cognito-user-pool-id = aws_cognito_user_pool.main.id
    cognito-client-id    = aws_cognito_user_pool_client.web.id
    cognito-domain       = "${aws_cognito_user_pool_domain.main.domain}.auth.ap-northeast-2.amazoncognito.com"
  }

  name  = "/tms/app/config/${each.key}"
  type  = "String"
  value = each.value
}
