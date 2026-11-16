# 계정에 하나만 두고 지우지 않는 기반 자원 (specs/a-platform/009-service-infra, research R1)
# - Route 53 호스팅 영역: 지웠다 만들면 네임서버 4개가 바뀌어 카페24 설정을 다시 해야 한다.
# - GitHub OIDC 공급자: 계정에 URL당 1개.
# - 비용 예산: 다른 스택을 지워도 알림은 남아야 한다.

resource "aws_route53_zone" "main" {
  name    = var.domain_name
  comment = "smokestack-guard service domain (NS delegated from Cafe24)"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# 크레딧을 빼기 전 금액으로 알린다. 기본값(include_credit = true)이면 크레딧이 비용을 상쇄해 0처럼 보인다.
resource "aws_budgets_budget" "monthly" {
  name         = "tms-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_types {
    include_credit = false
    include_refund = false
  }

  dynamic "notification" {
    for_each = [25, 50, 75]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
