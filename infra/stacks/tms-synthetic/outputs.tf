output "function_name" {
  description = "합성 적재 Lambda 이름 (수동 실행·백필·점검)"
  value       = aws_lambda_function.this.function_name
}

output "dlq_url" {
  description = "실패 보관함(SQS) URL. 재처리는 011 contracts §3"
  value       = aws_sqs_queue.dlq.url
}

output "schedule_state" {
  description = "정기·점검 스케줄 상태"
  value       = aws_scheduler_schedule.regular.state
}

output "ref_stats_key" {
  description = "참조 통계를 올릴 S3 키 (설정의 stats_version)"
  value       = "s3://${var.raw_bucket_name}/${local.root}/_ref_stats/${yamldecode(file("${local.source_dir}/config/daily.yaml")).run.stats_version}.csv"
}
