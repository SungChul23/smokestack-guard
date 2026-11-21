output "domain_endpoint" {
  description = "OpenSearch 도메인 주소 (setup_opensearch.py가 describe-domain으로도 찾음)"
  value       = var.opensearch_enabled ? aws_opensearch_domain.logs[0].endpoint : null
}

output "dashboards_url" {
  description = "OpenSearch Dashboards 주소 (Google 로그인, members)"
  value       = var.opensearch_enabled ? "https://${aws_opensearch_domain.logs[0].dashboard_endpoint}" : null
}

output "dashboards_client_ids" {
  description = "OpenSearch가 사용자 풀에 만든 앱 클라이언트 (비어 있으면 도메인 생성 뒤 한 번 더 apply)"
  value       = local.dashboards_client_ids
}

output "logs_bucket" {
  description = "Firehose 전달 실패분 버킷 (28일)"
  value       = aws_s3_bucket.logs.id
}
