output "name_servers" {
  description = "카페24 '다른 네임서버 사용'에 입력할 네임서버 4개"
  value       = aws_route53_zone.main.name_servers
}

output "zone_id" {
  description = "Route 53 호스팅 영역 ID"
  value       = aws_route53_zone.main.zone_id
}

output "github_oidc_provider_arn" {
  description = "GitHub Actions OIDC 공급자 ARN (tms-app 배포 역할이 신뢰)"
  value       = aws_iam_openid_connect_provider.github.arn
}
