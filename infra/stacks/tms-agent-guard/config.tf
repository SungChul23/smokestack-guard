# 에이전트 서버가 읽을 가드레일 설정 (spec 017 FR-011, data-model §3).
# 비밀이 아니므로 String. 서버 역할은 /tms/app/* 읽기 권한이 이미 있다.

resource "aws_ssm_parameter" "guardrail_id" {
  name        = "/tms/app/config/guardrail-id"
  description = "Agent guardrail id (017)"
  type        = "String"
  value       = aws_bedrock_guardrail.agent.guardrail_id
}

resource "aws_ssm_parameter" "guardrail_version" {
  name        = "/tms/app/config/guardrail-version"
  description = "Agent guardrail version number (017)"
  type        = "String"
  value       = aws_bedrock_guardrail_version.agent.version
}

resource "aws_ssm_parameter" "guardrail_enforce" {
  name        = "/tms/app/config/guardrail-enforce"
  description = "Policies to enforce: content,prompt_attack,topics,grounding or none (017)"
  type        = "String"
  value       = var.guardrail_enforce
}
