# 상태 머신과 스케줄 (contracts/load-interface.md §1·§2, research R3).
# RDS 존재 확인과 SNS 발행은 VPC 밖에서 해야 하므로 상태 머신이 맡는다.

locals {
  db_arn = "arn:aws:rds:${local.region}:${local.account_id}:db:${var.db_instance_identifier}"

  definition = {
    Comment = "Dashboard observation load (spec 012)"
    StartAt = "CheckDb"
    States = {
      CheckDb = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:rds:describeDBInstances"
        Parameters = {
          DbInstanceIdentifier = var.db_instance_identifier
        }
        ResultSelector = { "inst.$" = "$.DbInstances[0]" }
        ResultPath     = "$.db"
        Catch = [
          { ErrorEquals = ["Rds.DbInstanceNotFoundException", "Rds.DbInstanceNotFoundFault"], ResultPath = null, Next = "SkippedRdsOff" },
          { ErrorEquals = ["States.ALL"], ResultPath = "$.error", Next = "NotifyFailure" },
        ]
        Next = "IsAvailable"
      }
      IsAvailable = {
        Type    = "Choice"
        Choices = [{ Variable = "$.db.inst.DbInstanceStatus", StringEquals = "available", Next = "DbInfo" }]
        Default = "SkippedNotAvailable"
      }
      SkippedRdsOff = {
        Type   = "Pass"
        Result = { skipped = "rds_off" }
        End    = true
      }
      SkippedNotAvailable = {
        Type       = "Pass"
        Parameters = { "skipped.$" = "States.Format('rds_{}', $.db.inst.DbInstanceStatus)" }
        End        = true
      }
      DbInfo = {
        Type = "Pass"
        Parameters = {
          "db_host.$" = "$.db.inst.Endpoint.Address"
          "db_port.$" = "$.db.inst.Endpoint.Port"
        }
        ResultPath = "$.dbinfo"
        Next       = "Load"
      }
      Load = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.load.arn
          "Payload.$"  = "States.JsonMerge($$.Execution.Input, $.dbinfo, false)"
        }
        ResultSelector = { "Payload.$" = "$.Payload" }
        ResultPath     = "$.load"
        Retry = [{
          ErrorEquals     = ["Lambda.TooManyRequestsException", "Lambda.ServiceException", "Lambda.SdkClientException"]
          IntervalSeconds = 30
          MaxAttempts     = 2
          BackoffRate     = 1
        }]
        Catch = [{ ErrorEquals = ["States.ALL"], ResultPath = "$.error", Next = "NotifyFailure" }]
        Next  = "NeedNotify"
      }
      NeedNotify = {
        Type = "Choice"
        Choices = [{
          And = [
            { Variable = "$.mode", StringEquals = "daily" },
            { Variable = "$.load.Payload.new_names[0]", IsPresent = true },
            {
              Or = [
                { Variable = "$.notify", IsPresent = false },
                { Variable = "$.notify", BooleanEquals = true },
              ]
            },
          ]
          Next = "NotifyNewNames"
        }]
        Default = "Done"
      }
      NotifyNewNames = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn    = data.aws_sns_topic.alerts.arn
          Subject     = "[tms] dashboard load: new facility names"
          "Message.$" = "States.Format('ref.site_name_map에 없는 사업장 이름이 관측에 나타났습니다. 새 사업장인지 이름이 바뀐 것인지 확인해 이름 이력에 추가하세요.\n\n{}', States.JsonToString($.load.Payload.new_names))"
        }
        ResultPath = null
        Next       = "Done"
      }
      Done = { Type = "Succeed" }
      NotifyFailure = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn    = data.aws_sns_topic.alerts.arn
          Subject     = "[tms] dashboard load failed"
          "Message.$" = "States.Format('실행 {} 실패\n입력 {}\n오류 {}\n원인 {}', $$.Execution.Name, States.JsonToString($$.Execution.Input), $.error.Error, $.error.Cause)"
        }
        ResultPath = null
        Next       = "Failed"
      }
      Failed = { Type = "Fail", Error = "DashboardLoadFailed" }
    }
  }
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "tms-sfn-dashboard-load"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn" {
  statement {
    sid       = "DescribeDb"
    actions   = ["rds:DescribeDBInstances"]
    resources = [local.db_arn]
  }
  statement {
    sid       = "InvokeLoader"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.load.arn, "${aws_lambda_function.load.arn}:*"]
  }
  statement {
    sid       = "Alert"
    actions   = ["sns:Publish"]
    resources = [data.aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "tms-sfn-dashboard-load"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}

resource "aws_sfn_state_machine" "load" {
  name       = local.name
  role_arn   = aws_iam_role.sfn.arn
  type       = "STANDARD"
  definition = jsonencode(local.definition)
}

# ── 스케줄 ──
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "tms-scheduler-dashboard-load"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.load.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "tms-scheduler-dashboard-load"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

locals {
  schedules = {
    recent = { expression = "cron(15,45 * * * ? *)", input = { mode = "recent" } } # 새 폴더(:10·:40) 5분 뒤
    daily  = { expression = "cron(20 3 * * ? *)", input = { mode = "daily" } }     # 전날 마지막 값 지연 뒤
  }
}

resource "aws_scheduler_schedule" "load" {
  for_each = local.schedules

  name                         = "${local.name}-${each.key}"
  schedule_expression          = each.value.expression
  schedule_expression_timezone = "Asia/Seoul"
  state                        = var.load_schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.load.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode(each.value.input)
  }
}
