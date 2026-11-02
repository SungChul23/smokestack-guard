output "function_name" {
  description = "수집 Lambda 함수 이름"
  value       = aws_lambda_function.this.function_name
}

output "schedule_name" {
  description = "EventBridge Scheduler 스케줄 이름"
  value       = aws_scheduler_schedule.this.name
}
