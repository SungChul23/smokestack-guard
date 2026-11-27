# 팀원이 로컬 PC에서 본인 IAM 사용자로 이 지식 기반을 검색하는 그룹 (spec 016)
#
# - 서버는 서버 역할(agent_access.tf)로 부르고, 로컬 개발·시험은 사람의 IAM 사용자로 부르므로 따로 준다.
# - 서버 역할과 같은 범위: 이 지식 기반 Retrieve, 지식 기반 ID SSM 1개 읽기.
#   임베딩 호출과 OpenSearch 질의는 지식 기반 서비스 역할(tms-rag-kb)이 하므로 사람에게는 주지 않는다.
# - 그룹은 늘 있고, 정책은 지식 기반·에이전트 연결이 켜졌을 때만 (대상이 함께 생기고 사라짐).

resource "aws_iam_group" "rag_users" {
  name = "tms-rag-users"
}

resource "aws_iam_group_membership" "rag_users" {
  name  = "tms-rag-users"
  group = aws_iam_group.rag_users.name
  users = var.rag_user_names
}

data "aws_iam_policy_document" "rag_users" {
  count = local.agent_access ? 1 : 0

  statement {
    sid       = "RetrieveDocs"
    actions   = ["bedrock:Retrieve"]
    resources = [aws_bedrockagent_knowledge_base.docs[0].arn]
  }

  statement {
    sid       = "ReadKnowledgeBaseId"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [aws_ssm_parameter.kb_id[0].arn]
  }
}

resource "aws_iam_group_policy" "rag_users" {
  count  = local.agent_access ? 1 : 0
  name   = "tms-rag-retrieve"
  group  = aws_iam_group.rag_users.name
  policy = data.aws_iam_policy_document.rag_users[0].json
}
