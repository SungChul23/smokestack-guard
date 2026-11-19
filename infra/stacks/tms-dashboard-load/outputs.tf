output "state_machine_arn" {
  description = "적재 상태 머신 (backfill이 시작한다)"
  value       = aws_sfn_state_machine.load.arn
}

output "lambda_name" {
  description = "적재 Lambda 이름"
  value       = aws_lambda_function.load.function_name
}
