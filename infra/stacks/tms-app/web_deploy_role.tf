# 화면 전용 GitHub Actions 배포 역할 (#94). 화면은 별도 저장소 smokestack-guard-web-v2에서 개발·배포한다.
# - 신뢰: 그 저장소의 main 브랜치만(OIDC, 장기 키 없음). 서버 배포 역할(tms-github-deploy)과 나눠
#   화면 저장소가 ECR·서버 배포 권한을 갖지 않게 한다.
# - 권한: 화면 버킷 올리기·지우기, 화면 배포 1개 캐시 무효화, 빌드에 넣을 설정값 4개 읽기(비밀 아님).
# 계약: specs/a-platform/009-service-infra/contracts/deploy-pipeline.md

data "aws_iam_policy_document" "web_deploy_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_web_repository}:ref:refs/heads/main",
        "repo:${var.github_web_repository_immutable}:ref:refs/heads/main",
      ]
    }
  }
}

resource "aws_iam_role" "web_deploy" {
  name                 = "tms-github-web-deploy"
  assume_role_policy   = data.aws_iam_policy_document.web_deploy_assume.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "web_deploy" {
  statement {
    sid     = "ReadWebBuildConfig"
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [for n in ["cognito-user-pool-id", "cognito-client-id", "cognito-domain", "web-distribution-id"] :
      "arn:aws:ssm:ap-northeast-2:${local.account_id}:parameter/tms/app/config/${n}"
    ]
  }

  statement {
    sid       = "WebBucketList"
    actions   = ["s3:ListBucket"]
    resources = [data.aws_s3_bucket.web.arn]
  }

  statement {
    sid       = "WebBucketWrite"
    actions   = ["s3:PutObject", "s3:DeleteObject", "s3:GetObject"]
    resources = ["${data.aws_s3_bucket.web.arn}/*"]
  }

  statement {
    sid       = "InvalidateWeb"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = ["arn:aws:cloudfront::${local.account_id}:distribution/${data.aws_ssm_parameter.web_distribution_id.insecure_value}"]
  }
}

resource "aws_iam_role_policy" "web_deploy" {
  name   = "tms-github-web-deploy"
  role   = aws_iam_role.web_deploy.id
  policy = data.aws_iam_policy_document.web_deploy.json
}
