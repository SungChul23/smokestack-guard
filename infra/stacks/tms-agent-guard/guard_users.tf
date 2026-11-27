# 팀원이 로컬 PC에서 본인 IAM 사용자로 이 가드레일을 시험하는 그룹 (spec 017)
#
# - 서버는 서버 역할(agent_access.tf)로 부르고, 로컬 개발·시험은 사람의 IAM 사용자로 부르므로 따로 준다.
# - 서버 역할과 같은 범위: 이 가드레일(+ 교차 리전 프로필) 검사, 가드레일 설정 SSM 3개 읽기.
#   가드레일을 만들거나 고치는 권한은 주지 않는다.

resource "aws_iam_group" "guard_users" {
  name = "tms-agent-guard-users"
}

resource "aws_iam_group_membership" "guard_users" {
  name  = "tms-agent-guard-users"
  group = aws_iam_group.guard_users.name
  users = var.guard_user_names
}

data "aws_iam_policy_document" "guard_users" {
  statement {
    sid       = "ApplyAgentGuardrail"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = concat([aws_bedrock_guardrail.agent.guardrail_arn], local.profile_arns)
  }

  statement {
    sid     = "ReadGuardrailConfig"
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [
      aws_ssm_parameter.guardrail_id.arn,
      aws_ssm_parameter.guardrail_version.arn,
      aws_ssm_parameter.guardrail_enforce.arn,
    ]
  }
}

resource "aws_iam_group_policy" "guard_users" {
  name   = "tms-agent-guard-apply"
  group  = aws_iam_group.guard_users.name
  policy = data.aws_iam_policy_document.guard_users.json
}
