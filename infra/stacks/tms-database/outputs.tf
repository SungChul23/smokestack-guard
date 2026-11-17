output "db_host" {
  description = "DBeaver Main 탭 Host (DB가 꺼져 있으면 null)"
  value       = local.db_host
}

output "db_secret_arn" {
  description = "관리자 비밀번호가 든 비밀 ARN (값이 아니라 위치)"
  value       = local.db_secret_arn
}

output "bastion_host" {
  description = "DBeaver SSH 탭 Host"
  value       = var.rds_enabled ? "bastion.${var.domain_name}" : null
}
