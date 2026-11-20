# 학습용 합성 K-TMS: 008 잡·상태 머신을 source=ktms_synth로 재사용. specs/a-platform/011-synthetic-train-s3-ingest (US4)
#
# tms_synthetic_train_v2/(합성 적재 Lambda가 씀, 읽기만) → tms_silver2.ktms_synth → tms_silver2.ktms_synth_ml_ready
# 2026-11-20 생성기 v2로 원본 경로를 바꾸고 10/30부터 같은 표를 다시 계산했다(spec 015). v1 원본은 tms_synthetic_train/에 보존.
# - 실측 권한 문장은 건드리지 않고 같은 역할에 합성 전용 인라인 정책을 하나씩 더한다.
# - Silver 잡은 C의 read_bronze가 경로 인자를 받을 때만 합성 경로를 연다(ktms_pipeline.check_source_prefix).
#   그 전에는 합성 실행이 Silver 단계에서 실패하므로 스케줄은 꺼 둔다(ktms_synth_schedule_enabled).

locals {
  synth_source_prefix   = "tms_synthetic_train_v2"
  synth_silver_table    = "silver2/ktms_synth"
  synth_silver_runs     = "silver2/_runs/ktms_synth"
  synth_ml_ready_table  = "silver2/ktms_synth_ml_ready"
  synth_ml_ready_runs   = "silver2/_runs/ktms_synth_ml_ready"
  synth_check_runs_read = "silver2/_runs/ktms_synth_ml_ready"
}

# ---------------------------------------------------------------------------
# Silver 잡: 합성 Bronze 읽기, 합성 Silver 쓰기
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ktms_silver_synth" {
  statement {
    sid       = "ListSynth"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.synth_source_prefix}/*",
        local.synth_silver_table,
        "${local.synth_silver_table}/*",
        "${local.synth_silver_runs}/*",
      ]
    }
  }

  statement {
    sid       = "ReadSynthBronze"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/${local.synth_source_prefix}/ingest_date=*"]
  }

  statement {
    sid = "ReadWriteSynthSilver"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${local.raw_arn}/${local.synth_silver_table}/*",
      "${local.raw_arn}/${local.synth_silver_runs}/*",
    ]
  }

  statement {
    sid     = "IcebergCatalogSynthSilver"
    actions = ["glue:GetDatabase", "glue:GetTable", "glue:CreateTable", "glue:UpdateTable"]
    resources = [
      "${local.ktms_glue_catalog}:catalog",
      "${local.ktms_glue_catalog}:database/tms_silver2",
      "${local.ktms_glue_catalog}:table/tms_silver2/ktms_synth",
    ]
  }
}

resource "aws_iam_role_policy" "ktms_silver_synth" {
  name   = "tms-glue-silver2-ktms-synth"
  role   = aws_iam_role.ktms_silver.id
  policy = data.aws_iam_policy_document.ktms_silver_synth.json
}

# ---------------------------------------------------------------------------
# ML-ready 잡: 합성 Silver 읽기, 합성 ML-ready 쓰기
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ktms_ml_ready_synth" {
  statement {
    sid       = "ListSynth"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.synth_silver_table,
        "${local.synth_silver_table}/*",
        local.synth_ml_ready_table,
        "${local.synth_ml_ready_table}/*",
        "${local.synth_ml_ready_runs}/*",
      ]
    }
  }

  statement {
    sid       = "ReadSynthSilver"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/${local.synth_silver_table}/*"]
  }

  statement {
    sid = "ReadWriteSynthMlReady"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${local.raw_arn}/${local.synth_ml_ready_table}/*",
      "${local.raw_arn}/${local.synth_ml_ready_runs}/*",
    ]
  }

  statement {
    sid     = "IcebergCatalogSynth"
    actions = ["glue:GetDatabase", "glue:GetTable", "glue:CreateTable", "glue:UpdateTable"]
    resources = [
      "${local.ktms_glue_catalog}:catalog",
      "${local.ktms_glue_catalog}:database/tms_silver2",
      "${local.ktms_glue_catalog}:table/tms_silver2/ktms_synth",
      "${local.ktms_glue_catalog}:table/tms_silver2/ktms_synth_ml_ready",
    ]
  }
}

resource "aws_iam_role_policy" "ktms_ml_ready_synth" {
  name   = "tms-glue-silver2-ktms-synth-ml-ready"
  role   = aws_iam_role.ktms_ml_ready.id
  policy = data.aws_iam_policy_document.ktms_ml_ready_synth.json
}

# ---------------------------------------------------------------------------
# 계약 검사 Lambda(010): 합성 ML-ready와 그 실행 기록 읽기. 실측 비교(real_table)는 기존 권한
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ktms_check_synth" {
  statement {
    sid       = "ListSynthMlReady"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.synth_ml_ready_table}/*", "${local.synth_check_runs_read}/*"]
    }
  }

  statement {
    sid     = "ReadSynthMlReady"
    actions = ["s3:GetObject"]
    resources = [
      "${local.raw_arn}/${local.synth_ml_ready_table}/*",
      "${local.raw_arn}/${local.synth_check_runs_read}/*",
    ]
  }

  statement {
    sid     = "CatalogReadSynth"
    actions = ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions"]
    resources = [
      "${local.ktms_glue_catalog}:catalog",
      "${local.ktms_glue_catalog}:database/tms_silver2",
      "${local.ktms_glue_catalog}:table/tms_silver2/ktms_synth_ml_ready",
    ]
  }
}

resource "aws_iam_role_policy" "ktms_check_synth" {
  name   = "tms-lambda-ktms-ml-ready-check-synth"
  role   = aws_iam_role.ktms_check.id
  policy = data.aws_iam_policy_document.ktms_check_synth.json
}

# ---------------------------------------------------------------------------
# 합성 매일 갱신: 03:30 KST (실측 03:00과 Glue 실행이 겹치지 않게), 같은 상태 머신에 source=ktms_synth
# ---------------------------------------------------------------------------

resource "aws_scheduler_schedule" "ktms_synth_daily" {
  name                         = "tms-silver2-ktms-synth-daily"
  description                  = "Synthetic K-TMS Silver/ML-ready daily rebuild of the last 2 complete KST days (spec 011)"
  schedule_expression          = "cron(30 3 * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"
  state                        = var.ktms_synth_schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.ktms.arn
    role_arn = aws_iam_role.ktms_scheduler.arn
    input    = jsonencode({ source = "ktms_synth" })
  }
}

# ---------------------------------------------------------------------------
# 실측·합성 양성·음성 비율 (Athena 저장된 쿼리, 실행은 사람이 콘솔에서) — T031·T032
# ---------------------------------------------------------------------------

locals {
  label_balance_sql = file("${path.module}/../../../scripts/label_balance_queries.sql")
  # "-- name: <이름>" 줄로 나눈 쿼리들
  label_balance_queries = {
    for chunk in slice(split("-- name: ", local.label_balance_sql), 1, length(split("-- name: ", local.label_balance_sql))) :
    trimspace(split("\n", chunk)[0]) => trimspace(join("\n", slice(split("\n", chunk), 1, length(split("\n", chunk)))))
  }
}

resource "aws_athena_named_query" "label_balance" {
  for_each    = local.label_balance_queries
  name        = "tms_label_balance_${each.key}"
  description = "K-TMS 실측+합성 ML-ready 양성·음성 비율 (spec 011). {start}·{end}를 바꿔 실행"
  workgroup   = var.athena_workgroup
  database    = "tms_silver2"
  query       = each.value
}
