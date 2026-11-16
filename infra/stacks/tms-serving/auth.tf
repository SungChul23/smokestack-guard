# 로그인: 관리자만 계정을 만드는 사용자 풀 + 화면용 공개 앱 클라이언트 (research R8)

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
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = var.auth_redirect_urls
  logout_urls                          = var.auth_redirect_urls
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
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
