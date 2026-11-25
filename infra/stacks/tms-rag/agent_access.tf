# 에이전트 서버(D, #66)가 이 지식 기반을 검색한다 (spec 016 US4, contracts/agent-connection.md)
#
# - 서버 역할 tms-app-server는 tms-app 스택이 만든다. 여기서는 이름으로 찾아 인라인 정책 하나만 붙인다
#   (tms-app의 정책 tms-app-server와 따로 관리되어 서로 덮어쓰지 않는다).
# - Retrieve만 준다. 답변은 에이전트가 이름표 머리말을 붙여 자기 모델로 만든다(RetrieveAndGenerate는
#   이름표를 모델에 넘기지 않아 출처 구분·인용이 빠진다, research R9). 모델 호출 권한은 tms-app에 이미 있다.
# - 검색에 필요한 임베딩 호출과 OpenSearch 질의는 지식 기반 서비스 역할(tms-rag-kb)이 한다.
# - 지식 기반 ID는 비밀이 아니므로 String 파라미터로 둔다. 서버는 /tms/app/* 읽기 권한이 이미 있다.

locals {
  agent_access = var.rag_kb_enabled && var.agent_retrieve_enabled
}

data "aws_iam_role" "app_server" {
  count = local.agent_access ? 1 : 0
  name  = "tms-app-server"
}

data "aws_iam_policy_document" "agent_retrieve" {
  count = local.agent_access ? 1 : 0

  statement {
    sid       = "RetrieveDocs"
    actions   = ["bedrock:Retrieve"]
    resources = [aws_bedrockagent_knowledge_base.docs[0].arn]
  }
}

resource "aws_iam_role_policy" "agent_retrieve" {
  count  = local.agent_access ? 1 : 0
  name   = "tms-rag-retrieve"
  role   = data.aws_iam_role.app_server[0].id
  policy = data.aws_iam_policy_document.agent_retrieve[0].json
}

resource "aws_ssm_parameter" "kb_id" {
  count       = local.agent_access ? 1 : 0
  name        = "/tms/app/config/rag-knowledge-base-id"
  description = "RAG knowledge base id for the agent server (016)"
  type        = "String"
  value       = aws_bedrockagent_knowledge_base.docs[0].id
}
