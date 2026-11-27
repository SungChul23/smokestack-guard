# 에이전트 서버(D, #66)가 이 가드레일로 검사한다 (spec 017 US1, research R5)
#
# - 서버 역할 tms-app-server는 tms-app 스택이 만든다. 이름으로 찾아 인라인 정책 하나만 붙인다
#   (tms-app의 정책, tms-rag의 tms-rag-retrieve와 따로 관리되어 서로 덮어쓰지 않는다).
# - ApplyGuardrail만 준다. 가드레일을 만들거나 고치는 권한은 주지 않는다.
# - STANDARD 등급은 교차 리전 프로필을 거치므로 프로필 ARN에도 허용한다(리전은 프로필이 고름).

locals {
  profile_arns = local.standard ? [
    "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:guardrail-profile/${var.guardrail_profile_id}",
  ] : []
}

data "aws_iam_role" "app_server" {
  count = var.agent_access_enabled ? 1 : 0
  name  = var.app_server_role_name
}

data "aws_iam_policy_document" "apply_guardrail" {
  count = var.agent_access_enabled ? 1 : 0

  statement {
    sid       = "ApplyAgentGuardrail"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = concat([aws_bedrock_guardrail.agent.guardrail_arn], local.profile_arns)
  }
}

resource "aws_iam_role_policy" "apply_guardrail" {
  count  = var.agent_access_enabled ? 1 : 0
  name   = "tms-agent-guard"
  role   = data.aws_iam_role.app_server[0].id
  policy = data.aws_iam_policy_document.apply_guardrail[0].json
}
