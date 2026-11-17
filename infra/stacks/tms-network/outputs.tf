output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "subnet_ids" {
  description = "서브넷 ID (public-a/c, app-a/c, db-a/c)"
  value       = { for k, v in aws_subnet.this : k => v.id }
}

output "security_group_ids" {
  description = "보안그룹 ID (alb, app, bastion, db)"
  value       = local.sg
}

output "nat_gateway_count" {
  description = "현재 NAT 개수"
  value       = var.nat_gateway_count
}
