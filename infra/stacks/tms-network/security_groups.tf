# 보안그룹 4개와 규칙 (data-model.md §3). 출발지는 IP 대신 다른 보안그룹을 가리킨다.
# 설명(description)은 AWS가 ASCII만 받아서 영어로 쓴다.

resource "aws_security_group" "this" {
  for_each = {
    alb     = "ALB - HTTPS from internet to app servers"
    app     = "API and agent servers - 8000 from ALB only"
    bastion = "Bastion - SSH tunnel to RDS only"
    db      = "RDS - 5432 from app servers and bastion only"
  }

  name        = "tms-${each.key}"
  description = each.value
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "tms-${each.key}" }
}

locals {
  sg = { for k, v in aws_security_group.this : k => v.id }
}

# ── ALB ──
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = local.sg.alb
  description       = "Internet to ALB HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = local.sg.alb
  description       = "Internet to ALB HTTP (redirect to HTTPS)"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_egress_rule" "alb_to_app" {
  security_group_id            = local.sg.alb
  description                  = "ALB to app port"
  referenced_security_group_id = local.sg.app
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

# ── 서버 ──
resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = local.sg.app
  description                  = "ALB to app port"
  referenced_security_group_id = local.sg.alb
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "app_https" {
  security_group_id = local.sg.app
  description       = "App to AWS APIs, Bedrock, ECR via NAT"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "app_to_db" {
  security_group_id            = local.sg.app
  description                  = "App to RDS"
  referenced_security_group_id = local.sg.db
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

# ── 배스천 ──
resource "aws_vpc_security_group_ingress_rule" "bastion_ssh" {
  for_each = toset(var.bastion_ssh_cidrs)

  security_group_id = local.sg.bastion
  description       = "Team SSH tunnel (shared key, DB only)"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_egress_rule" "bastion_https" {
  security_group_id = local.sg.bastion
  description       = "Bastion to SSM and package repos"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "bastion_to_db" {
  security_group_id            = local.sg.bastion
  description                  = "Bastion to RDS (SSH tunnel)"
  referenced_security_group_id = local.sg.db
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

# ── DB ──
resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = local.sg.db
  description                  = "App to RDS"
  referenced_security_group_id = local.sg.app
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "db_from_bastion" {
  security_group_id            = local.sg.db
  description                  = "Bastion to RDS"
  referenced_security_group_id = local.sg.bastion
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
