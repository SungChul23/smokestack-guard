# Bedrock 지식 기반 서비스 역할 (spec 016, research R5)
#
# - 문서 버킷 읽기, 임베딩 모델 호출, OpenSearch 도메인 HTTP. (파싱은 로컬에서 하므로 파서 모델 권한 없음)
# - 도메인 접근 정책(tms-log-search)은 이 역할을 이름으로 찾아 허용한다.
# - 도메인 안에서 무엇을 할 수 있는지는 FGAC 역할 rag_kb_writer(rag-docs*만)가 정한다(setup_opensearch.py).

locals {
  region      = "ap-northeast-2"
  kb_role     = "tms-rag-kb"
  domain_arn  = "arn:aws:es:${local.region}:${local.account_id}:domain/${var.opensearch_domain_name}"
  embed_arn   = "arn:aws:bedrock:${local.region}::foundation-model/${var.embedding_model_id}"
  answer_arn  = "arn:aws:bedrock:${local.region}:${local.account_id}:inference-profile/${var.answer_profile_id}"
  answer_base = replace(var.answer_profile_id, "/^(global|apac|us|eu|jp|au)\\./", "")
}

data "aws_iam_policy_document" "kb_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock:${local.region}:${local.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role" "kb" {
  name = local.kb_role
  # IAM 설명은 ASCII만 허용된다(한글 불가)
  description        = "Bedrock knowledge base tms-rag-docs (016): read docs bucket, embedding model, OpenSearch rag-docs"
  assume_role_policy = data.aws_iam_policy_document.kb_assume.json
}

data "aws_iam_policy_document" "kb" {
  statement {
    sid       = "ReadDocs"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.docs.arn]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [local.account_id]
    }
  }
  statement {
    sid       = "ReadDocObjects"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.docs.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [local.account_id]
    }
  }
  statement {
    sid       = "Embed"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.embed_arn]
  }
  statement {
    sid = "VectorStore"
    actions = [
      "es:ESHttpGet", "es:ESHttpPost", "es:ESHttpPut", "es:ESHttpDelete", "es:ESHttpHead",
      "es:DescribeDomain",
    ]
    resources = [local.domain_arn, "${local.domain_arn}/*"]
  }
}

resource "aws_iam_role_policy" "kb" {
  name   = local.kb_role
  role   = aws_iam_role.kb.id
  policy = data.aws_iam_policy_document.kb.json
}
