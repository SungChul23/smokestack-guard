output "raw_bucket_name" {
  description = "원본 보존 S3 버킷 이름"
  value       = module.raw_archive.bucket_name
}

output "collector_function_name" {
  description = "수집 Lambda 함수 이름"
  value       = module.collector.function_name
}

output "collector_schedule_name" {
  description = "EventBridge Scheduler 스케줄 이름"
  value       = module.collector.schedule_name
}

output "alert_topic_arn" {
  description = "수집 알림 SNS 토픽 ARN"
  value       = aws_sns_topic.alerts.arn
}

output "missing_rate_function_name" {
  description = "누락률 리포트 Lambda 함수 이름"
  value       = module.missing_rate.function_name
}
