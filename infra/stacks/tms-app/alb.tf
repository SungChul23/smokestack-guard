# ALB + api. 레코드 (research R14). alb_enabled로 켜고 끈다.
# /api/* → API 서버, /agent/* → 에이전트 서버. 접두사는 떼지 않는다 (contracts/app-runtime.md).

data "aws_route53_zone" "main" {
  name = var.domain_name
}

data "aws_acm_certificate" "api" {
  domain      = "api.${var.domain_name}"
  statuses    = ["ISSUED"]
  most_recent = true
}

resource "aws_lb" "main" {
  count = var.alb_enabled ? 1 : 0

  name               = "tms-alb"
  load_balancer_type = "application"
  security_groups    = [data.aws_security_group.this["alb"].id]
  subnets            = [data.aws_subnet.this["public-a"].id, data.aws_subnet.this["public-c"].id]
  idle_timeout       = 120 # 에이전트 응답이 길 수 있다
}

# 대상 그룹은 ASG가 참조하므로 ALB와 같이 켜고 끈다
resource "aws_lb_target_group" "app" {
  for_each = var.alb_enabled ? local.apps : {}

  name                 = "tms-${each.key}"
  port                 = 8000
  protocol             = "HTTP"
  vpc_id               = data.aws_vpc.main.id
  deregistration_delay = 30

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  count = var.alb_enabled ? 1 : 0

  load_balancer_arn = aws_lb.main[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  count = var.alb_enabled ? 1 : 0

  load_balancer_arn = aws_lb.main[0].arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = data.aws_acm_certificate.api.arn

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      message_body = "{\"detail\":\"not found\"}"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener_rule" "app" {
  for_each = var.alb_enabled ? { api = 10, agent = 20 } : {}

  listener_arn = aws_lb_listener.https[0].arn
  priority     = each.value

  condition {
    path_pattern {
      values = ["/${each.key}/*"]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app[each.key].arn
  }
}

resource "aws_route53_record" "api" {
  count = var.alb_enabled ? 1 : 0

  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main[0].dns_name
    zone_id                = aws_lb.main[0].zone_id
    evaluate_target_health = false
  }
}
