output "docs_bucket" {
  description = "RAG 근거 문서 버킷 (laws/·handbook/)"
  value       = aws_s3_bucket.docs.bucket
}

output "kb_role_arn" {
  description = "지식 기반 서비스 역할. setup_opensearch.py가 FGAC 역할 rag_kb_writer에 매핑한다"
  value       = aws_iam_role.kb.arn
}

output "knowledge_base_id" {
  description = "지식 기반 ID (ask.py --kb / RAG_KB_ID). rag_kb_enabled=false면 null"
  value       = one(aws_bedrockagent_knowledge_base.docs[*].id)
}

output "data_source_ids" {
  description = "동기화(start-ingestion-job)에 쓰는 데이터 소스 ID: laws, handbook"
  value       = { for k, v in aws_bedrockagent_data_source.docs : k => v.data_source_id }
}
