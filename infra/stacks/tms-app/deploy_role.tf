# GitHub Actions 배포 역할 (contracts/deploy-pipeline.md). main 브랜치만, 장기 키 없음.

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_s3_bucket" "web" {
  bucket = var.web_bucket_name
}

data "aws_ssm_parameter" "web_distribution_id" {
  name = "/tms/app/config/web-distribution-id"
}

data "aws_iam_policy_document" "deploy_assume" {
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
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository_immutable}:ref:refs/heads/main",
      ]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "tms-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.deploy_assume.json
  max_session_duration = 3600
}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
    ]
    resources = [for r in aws_ecr_repository.app : r.arn]
  }

  statement {
    sid       = "WriteImageTag"
    actions   = ["ssm:PutParameter", "ssm:GetParameter"]
    resources = [for p in aws_ssm_parameter.image_tag : p.arn]
  }

  # 화면 빌드에 넣을 Cognito 값, 캐시 무효화할 배포 ID (비밀 아님)
  statement {
    sid       = "ReadAppConfig"
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = ["arn:aws:ssm:ap-northeast-2:${local.account_id}:parameter/tms/app/config/*"]
  }

  statement {
    sid       = "FindServers"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }

  statement {
    sid       = "RunDeployDocument"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ssm:ap-northeast-2::document/AWS-RunShellScript"]
  }

  statement {
    sid       = "RunOnAppServersOnly"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ec2:ap-northeast-2:${local.account_id}:instance/*"]

    condition {
      test     = "StringLike"
      variable = "ssm:resourceTag/tms:app"
      values   = ["api", "agent"]
    }
  }

  statement {
    sid       = "ReadCommandResults"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations", "ssm:ListCommands"]
    resources = ["*"]
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

resource "aws_iam_role_policy" "deploy" {
  name   = "tms-github-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
