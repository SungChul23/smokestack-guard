# 서버 역할 tms-app-server (data-model.md §5)

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "tms-app-server"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# 배포 명령 수신(SendCommand)과 A의 세션 접속
resource "aws_iam_role_policy_attachment" "app_ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# tms-serving이 쓴 사용자 풀 ID (원격 상태 대신 SSM, 009와 같은 방식)
data "aws_ssm_parameter" "cognito_user_pool_id" {
  name = "/tms/app/config/cognito-user-pool-id"
}

data "aws_iam_policy_document" "app" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid       = "EcrPull"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
    resources = [for r in aws_ecr_repository.app : r.arn]
  }

  statement {
    sid     = "ReadAppConfig"
    actions = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = [
      "arn:aws:ssm:ap-northeast-2:${data.aws_caller_identity.current.account_id}:parameter/tms/app",
      "arn:aws:ssm:ap-northeast-2:${data.aws_caller_identity.current.account_id}:parameter/tms/app/*",
    ]
  }

  # RDS가 만든 관리자 비밀 (이름이 rds!db- 로 시작)
  statement {
    sid       = "ReadDbSecret"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = ["arn:aws:secretsmanager:ap-northeast-2:${data.aws_caller_identity.current.account_id}:secret:rds!db-*"]
  }

  statement {
    sid       = "WriteContainerLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = [for g in aws_cloudwatch_log_group.app : "${g.arn}:*"]
  }

  # 초대 코드 통과 시 회원을 members 그룹에 넣는다 (013 research R7)
  statement {
    sid       = "AddMemberGroup"
    actions   = ["cognito-idp:AdminAddUserToGroup"]
    resources = ["arn:aws:cognito-idp:ap-northeast-2:${data.aws_caller_identity.current.account_id}:userpool/${data.aws_ssm_parameter.cognito_user_pool_id.insecure_value}"]
  }

  # SecureString(/tms/app/secret/*, 초대 코드) 복호화. AWS 관리형 키를 SSM 경유로만
  statement {
    sid       = "DecryptAppSecrets"
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:ap-northeast-2:${data.aws_caller_identity.current.account_id}:key/*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.ap-northeast-2.amazonaws.com"]
    }
    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "kms:ResourceAliases"
      values   = ["alias/aws/ssm"]
    }
  }

  # API·에이전트 서버가 RDS에 tms_app 계정(IAM 인증)으로 접속한다 (012 data-model §7).
  # 스냅샷에서 다시 만들면 리소스 ID가 바뀌므로 인스턴스 부분은 *로 두고 계정 이름으로 좁힌다
  # (tms-dashboard-load의 ConnectAsLoader와 같은 방식).
  statement {
    sid       = "ConnectAsApp"
    actions   = ["rds-db:connect"]
    resources = ["arn:aws:rds-db:ap-northeast-2:${data.aws_caller_identity.current.account_id}:dbuser:*/tms_app"]
  }

  # 에이전트 LLM 호출. 쓰는 모델이 정해지면 좁힌다.
  statement {
    sid       = "InvokeBedrock"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "app" {
  name   = "tms-app-server"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}

resource "aws_iam_instance_profile" "app" {
  name = "tms-app-server"
  role = aws_iam_role.app.name
}
