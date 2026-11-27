output "guardrail_id" {
  description = "가드레일 ID"
  value       = aws_bedrock_guardrail.agent.guardrail_id
}

output "guardrail_arn" {
  description = "가드레일 ARN"
  value       = aws_bedrock_guardrail.agent.guardrail_arn
}

output "guardrail_version" {
  description = "에이전트가 쓰는 가드레일 버전 번호"
  value       = aws_bedrock_guardrail_version.agent.version
}

output "ssm_parameters" {
  description = "에이전트가 읽는 SSM 파라미터 이름"
  value = [
    aws_ssm_parameter.guardrail_id.name,
    aws_ssm_parameter.guardrail_version.name,
    aws_ssm_parameter.guardrail_enforce.name,
  ]
}
