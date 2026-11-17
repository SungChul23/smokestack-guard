output "web_bucket" {
  description = "화면 버킷"
  value       = aws_s3_bucket.web.id
}

output "distribution_id" {
  description = "CloudFront 배포 ID (CI 캐시 무효화)"
  value       = aws_cloudfront_distribution.web.id
}

output "distribution_domain" {
  description = "CloudFront 기본 도메인"
  value       = aws_cloudfront_distribution.web.domain_name
}

output "api_certificate_arn" {
  description = "ALB용 api. 인증서 (서울)"
  value       = aws_acm_certificate_validation.api.certificate_arn
}

output "cognito_user_pool_id" {
  description = "Cognito 사용자 풀 ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "화면용 앱 클라이언트 ID"
  value       = aws_cognito_user_pool_client.web.id
}

output "cognito_login_domain" {
  description = "관리형 로그인 도메인"
  value       = "${aws_cognito_user_pool_domain.main.domain}.auth.ap-northeast-2.amazoncognito.com"
}
