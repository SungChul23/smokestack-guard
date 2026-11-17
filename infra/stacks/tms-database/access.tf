# 팀원이 DB 관리자 비밀번호와 주소를 읽는 IAM 그룹 (research R11)
# 그룹은 늘 있고, 정책은 DB가 켜졌을 때만 (대상 비밀이 DB와 함께 생기고 사라짐).

resource "aws_iam_group" "db_users" {
  name = "tms-db-users"
}

resource "aws_iam_group_membership" "db_users" {
  name  = "tms-db-users"
  group = aws_iam_group.db_users.name
  users = var.db_user_names
}

data "aws_iam_policy_document" "db_users" {
  count = var.rds_enabled ? 1 : 0

  statement {
    sid       = "ReadDbAdminSecret"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [local.db_secret_arn]
  }

  statement {
    sid       = "FindDbEndpoint"
    actions   = ["rds:DescribeDBInstances"]
    resources = ["*"]
  }
}

resource "aws_iam_group_policy" "db_users" {
  count = var.rds_enabled ? 1 : 0

  name   = "tms-db-read-secret"
  group  = aws_iam_group.db_users.name
  policy = data.aws_iam_policy_document.db_users[0].json
}
