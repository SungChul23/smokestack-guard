# Bedrock 지식 기반 + 데이터 소스 2개 (spec 016 US1, research R1·R2·R4)
#
# - 만들 때 인덱스 rag-docs와 FGAC 매핑을 검사한다 → setup_opensearch.py 뒤에 rag_kb_enabled=true로 apply.
# - 데이터 소스마다 조각 방식이 하나다: laws/ = 계층(작은 조각으로 찾고 큰 조각을 넘김), handbook/ = 의미 단위.
# - 올리는 문서는 PDF가 아니라 검사를 통과한 마크다운(.md)이다(파싱은 로컬 pdf_to_md.py, research R4b).
# - 조각 설정은 데이터 소스를 만든 뒤 바꾸면 다시 만들어진다(재동기화 필요).
# - AWS에 보내는 이름·설명은 ASCII만 쓴다(IAM에서 한글 설명이 거부된 적 있음).

locals {
  kb_on = var.rag_kb_enabled ? 1 : 0
}

data "aws_opensearch_domain" "logs" {
  count       = local.kb_on
  domain_name = var.opensearch_domain_name
}

resource "aws_bedrockagent_knowledge_base" "docs" {
  count       = local.kb_on
  name        = "tms-rag-docs"
  description = "Korean air-quality law, TMS notices and handbook for the agent (spec 016)"
  role_arn    = aws_iam_role.kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = local.embed_arn
      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = var.embedding_dimensions
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = "OPENSEARCH_MANAGED_CLUSTER"
    opensearch_managed_cluster_configuration {
      domain_arn        = data.aws_opensearch_domain.logs[0].arn
      domain_endpoint   = "https://${data.aws_opensearch_domain.logs[0].endpoint}"
      vector_index_name = var.index_name
      field_mapping {
        vector_field   = "bedrock-vector"
        text_field     = "bedrock-text"
        metadata_field = "bedrock-metadata"
      }
    }
  }

  depends_on = [aws_iam_role_policy.kb]
}

locals {
  # 데이터 소스 2개: 폴더(포함 접두어)와 조각 방식만 다르다
  data_sources = {
    laws = {
      description = "Statutes, decrees, rules, appendices and notices (hierarchical chunks)"
      strategy    = "HIERARCHICAL"
    }
    handbook = {
      description = "TMS operations handbook 2024.12, superseded edition (semantic chunks)"
      strategy    = "SEMANTIC"
    }
  }
}

resource "aws_bedrockagent_data_source" "docs" {
  for_each          = var.rag_kb_enabled ? local.data_sources : {}
  knowledge_base_id = aws_bedrockagent_knowledge_base.docs[0].id
  name              = "tms-rag-${each.key}"
  description       = each.value.description
  # 버킷에서 지운 문서는 다음 동기화 때 인덱스에서도 지운다 (FR-012)
  data_deletion_policy = "DELETE"

  # 만들 때 역할 권한을 검사한다. 역할 정책 갱신과 동시에 만들면 거부된다(2026-11-23)
  depends_on = [aws_iam_role_policy.kb]

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = aws_s3_bucket.docs.arn
      inclusion_prefixes = ["${each.key}/"]
    }
  }

  vector_ingestion_configuration {
    # 파싱은 지식 기반 밖에서 한다(research R4b): services/rag-docs/pdf_to_md.py가 쪽마다 Sonnet 4.6으로
    # 마크다운을 만들고 검사(표 칸 수·정답 행)를 통과한 .md만 올린다. md는 기본 파서로 그대로 읽는다.
    # 지식 기반 안의 모델 파서는 같은 모델·지시문에서도 표 칸을 빠뜨렸고(2026-11-23), BDA 파서는 이 계정에서 허용되지 않았다.

    chunking_configuration {
      chunking_strategy = each.value.strategy

      dynamic "hierarchical_chunking_configuration" {
        for_each = each.value.strategy == "HIERARCHICAL" ? [1] : []
        content {
          overlap_tokens = 60
          level_configuration {
            max_tokens = 1500 # 부모: 별표 표·조문 묶음
          }
          level_configuration {
            max_tokens = 300 # 자식: 검색 단위
          }
        }
      }

      dynamic "semantic_chunking_configuration" {
        for_each = each.value.strategy == "SEMANTIC" ? [1] : []
        content {
          max_token                       = 300
          buffer_size                     = 0
          breakpoint_percentile_threshold = 95
        }
      }
    }
  }
}
