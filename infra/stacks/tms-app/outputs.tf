output "ecr_repository_urls" {
  description = "앱 이미지 저장소 주소"
  value       = { for k, r in aws_ecr_repository.app : k => r.repository_url }
}

output "asg_names" {
  description = "서버 그룹 이름"
  value       = { for k, g in aws_autoscaling_group.app : k => g.name }
}

output "github_deploy_role_arn" {
  description = "GitHub Actions가 받을 배포 역할 ARN (워크플로에 상수로 씀, 비밀 아님)"
  value       = aws_iam_role.deploy.arn
}

output "alb_dns_name" {
  description = "ALB 기본 주소 (꺼져 있으면 null)"
  value       = var.alb_enabled ? aws_lb.main[0].dns_name : null
}
