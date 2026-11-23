output "docs_bucket" {
  description = "RAG 근거 문서 버킷 (laws/·handbook/)"
  value       = aws_s3_bucket.docs.bucket
}

output "kb_role_arn" {
  description = "지식 기반 서비스 역할. setup_opensearch.py가 FGAC 역할 rag_kb_writer에 매핑한다"
  value       = aws_iam_role.kb.arn
}

# 지식 기반·데이터 소스 ID는 knowledge_base.tf에서 더한다 (tasks T025)
