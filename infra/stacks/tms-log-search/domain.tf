# OpenSearch 도메인과 Dashboards 로그인 (specs/a-platform/014-log-opensearch, research R1·R2)
#
# - t3.small.search 1대, gp3 10GB, 1-AZ, 공개 주소. 보안은 IAM 서명 + Cognito 로그인 + 세분화된 접근 제어(FGAC).
# - FGAC 마스터 = 이 스택을 apply한 IAM 사용자(내부 사용자 DB 없음, 비밀번호 없음).
# - Dashboards 로그인은 013의 Cognito 사용자 풀(Google + 초대 코드). members 그룹만 뷰어 역할을 받는다.
# - OpenSearch가 사용자 풀에 자기 앱 클라이언트(AmazonOpenSearchService-tms-logs-…)를 만든다. 그 클라이언트에 Google을 더하는 것은
#   사람이 한다(quickstart §4). 역할 규칙은 그 클라이언트를 찾아 두 번째 apply에서 자동으로 붙는다.

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "cognito_user_pool_id" {
  name = "/tms/app/config/cognito-user-pool-id"
}

locals {
  on            = var.opensearch_enabled ? 1 : 0
  account_id    = data.aws_caller_identity.current.account_id
  domain_name   = "tms-logs"
  domain_arn    = "arn:aws:es:ap-northeast-2:${local.account_id}:domain/${local.domain_name}"
  user_pool_id  = data.aws_ssm_parameter.cognito_user_pool_id.insecure_value
  user_pool_arn = "arn:aws:cognito-idp:ap-northeast-2:${local.account_id}:userpool/${local.user_pool_id}"
}

# ---------------------------------------------------------------------------
# Cognito: 자격 증명 풀과 역할 (members → 뷰어, 그 밖 → 권한 없음)
# ---------------------------------------------------------------------------

resource "aws_cognito_identity_pool" "logs" {
  count                            = local.on
  identity_pool_name               = "tms_logs"
  allow_unauthenticated_identities = false

  # OpenSearch가 Cognito를 설정할 때 자기 앱 클라이언트를 여기에 더한다
  lifecycle {
    ignore_changes = [cognito_identity_providers]
  }
}

data "aws_iam_policy_document" "cognito_assume" {
  count = local.on

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["cognito-identity.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "cognito-identity.amazonaws.com:aud"
      values   = [aws_cognito_identity_pool.logs[0].id]
    }

    condition {
      test     = "ForAnyValue:StringLike"
      variable = "cognito-identity.amazonaws.com:amr"
      values   = ["authenticated"]
    }
  }
}

resource "aws_iam_role" "viewer" {
  count              = local.on
  name               = "tms-logs-viewer"
  description        = "OpenSearch Dashboards viewer for Cognito members (spec 014)"
  assume_role_policy = data.aws_iam_policy_document.cognito_assume[0].json
}

resource "aws_iam_role_policy" "viewer" {
  count = local.on
  name  = "tms-logs-viewer"
  role  = aws_iam_role.viewer[0].id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Sid = "UseDomain", Effect = "Allow", Action = ["es:ESHttp*"], Resource = "${local.domain_arn}/*" }]
  })
}

# 로그인은 됐지만 members가 아닌 사람(초대 코드 전). 권한이 없다
resource "aws_iam_role" "noaccess" {
  count              = local.on
  name               = "tms-logs-noaccess"
  description        = "Cognito users without members group: no OpenSearch access (spec 014)"
  assume_role_policy = data.aws_iam_policy_document.cognito_assume[0].json
}

# OpenSearch가 사용자 풀에 만든 앱 클라이언트 (도메인을 만든 뒤 두 번째 apply부터 보임)
data "aws_cognito_user_pool_clients" "pool" {
  user_pool_id = local.user_pool_id
}

locals {
  dashboards_client_ids = [
    for i, name in data.aws_cognito_user_pool_clients.pool.client_names : data.aws_cognito_user_pool_clients.pool.client_ids[i]
    if startswith(name, "AmazonOpenSearchService-") || startswith(name, "AWSElasticsearch-")
  ]
}

resource "aws_cognito_identity_pool_roles_attachment" "logs" {
  count            = local.on
  identity_pool_id = aws_cognito_identity_pool.logs[0].id
  roles = {
    authenticated = aws_iam_role.noaccess[0].arn
  }

  dynamic "role_mapping" {
    for_each = local.dashboards_client_ids
    content {
      identity_provider         = "cognito-idp.ap-northeast-2.amazonaws.com/${local.user_pool_id}:${role_mapping.value}"
      type                      = "Rules"
      ambiguous_role_resolution = "AuthenticatedRole"

      mapping_rule {
        claim      = "cognito:groups"
        match_type = "Contains"
        value      = "members"
        role_arn   = aws_iam_role.viewer[0].arn
      }
    }
  }
}

# OpenSearch가 Cognito를 설정할 때 쓰는 서비스 역할
resource "aws_iam_role" "opensearch_cognito" {
  count       = local.on
  name        = "tms-logs-opensearch-cognito"
  description = "Lets OpenSearch configure Cognito for Dashboards login (spec 014)"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = ["opensearchservice.amazonaws.com", "es.amazonaws.com"] }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "opensearch_cognito" {
  count      = local.on
  role       = aws_iam_role.opensearch_cognito[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonOpenSearchServiceCognitoAccess"
}

# 오류 몰림 알림(Alerting → SNS)에 OpenSearch가 쓰는 역할
resource "aws_iam_role" "sns" {
  count       = local.on
  name        = "tms-logs-sns"
  description = "Lets OpenSearch alerting publish to the ops SNS topic (spec 014)"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = ["opensearchservice.amazonaws.com", "es.amazonaws.com"] }
    }]
  })
}

resource "aws_iam_role_policy" "sns" {
  count = local.on
  name  = "tms-logs-sns"
  role  = aws_iam_role.sns[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "PublishOps"
      Effect   = "Allow"
      Action   = "sns:Publish"
      Resource = "arn:aws:sns:ap-northeast-2:${local.account_id}:${var.alert_topic_name}"
    }]
  })
}

# ---------------------------------------------------------------------------
# 도메인
# ---------------------------------------------------------------------------

resource "aws_opensearch_domain" "logs" {
  count          = local.on
  domain_name    = local.domain_name
  engine_version = var.engine_version

  cluster_config {
    instance_type          = var.instance_type
    instance_count         = 1
    zone_awareness_enabled = false
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.volume_gb
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = false

    master_user_options {
      master_user_arn = data.aws_caller_identity.current.arn
    }
  }

  cognito_options {
    enabled          = true
    user_pool_id     = local.user_pool_id
    identity_pool_id = aws_cognito_identity_pool.logs[0].id
    role_arn         = aws_iam_role.opensearch_cognito[0].arn
  }

  # 인증 없는 요청은 FGAC가 막는다. 여기서는 우리 주체만 도메인을 부를 수 있게 한다
  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { AWS = [
        data.aws_caller_identity.current.arn,
        aws_iam_role.firehose[0].arn,
        aws_iam_role.viewer[0].arn,
      ] }
      Action   = "es:ESHttp*"
      Resource = "${local.domain_arn}/*"
    }]
  })

  depends_on = [aws_iam_role_policy_attachment.opensearch_cognito]
}
