# RDS PostgreSQL + pgvector (research R9). rds_enabled로 켜고 끈다. 배스천은 bastion.tf, 팀원 권한은 access.tf.

data "aws_vpc" "main" {
  tags = { Name = "tms-vpc" }
}

data "aws_subnet" "this" {
  for_each = toset(["public-a", "db-a", "db-c"])

  vpc_id = data.aws_vpc.main.id
  tags   = { Name = "tms-${each.key}" }
}

data "aws_security_group" "this" {
  for_each = toset(["db", "bastion"])

  vpc_id = data.aws_vpc.main.id
  name   = "tms-${each.key}"
}

data "aws_route53_zone" "main" {
  name = var.domain_name
}

resource "aws_db_subnet_group" "main" {
  name        = "tms-db"
  description = "tms RDS subnets (AZ a, c)"
  subnet_ids  = [data.aws_subnet.this["db-a"].id, data.aws_subnet.this["db-c"].id]
}

resource "aws_db_instance" "main" {
  count = var.rds_enabled ? 1 : 0

  identifier     = "tms-db"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  db_name                     = "tms"
  username                    = "tms_admin"
  manage_master_user_password = true

  # 적재·앱 계정은 비밀번호 없이 IAM 토큰으로 접속한다 (012 research R4). 관리자는 비밀번호 그대로.
  iam_database_authentication_enabled = true

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [data.aws_security_group.this["db"].id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period    = 1
  auto_minor_version_upgrade = true
  apply_immediately          = true
  deletion_protection        = false

  # 끌 때 마지막 스냅샷을 남긴다. 이름에 생성 시각을 넣어 다음 삭제와 겹치지 않게 한다.
  skip_final_snapshot       = false
  final_snapshot_identifier = "tms-db-final-${formatdate("YYYYMMDDhhmm", timestamp())}"
  snapshot_identifier       = var.db_restore_snapshot_id != "" ? var.db_restore_snapshot_id : null

  lifecycle {
    ignore_changes = [final_snapshot_identifier, snapshot_identifier]
  }
}

locals {
  db_secret_arn = var.rds_enabled ? aws_db_instance.main[0].master_user_secret[0].secret_arn : null
  db_host       = var.rds_enabled ? aws_db_instance.main[0].address : null
}

# RDS가 만든 관리자 비밀번호를 30일마다 교체 (기본 7일이면 DBeaver에 저장한 값이 자주 안 맞음)
resource "aws_secretsmanager_secret_rotation" "db" {
  count = var.rds_enabled ? 1 : 0

  secret_id = local.db_secret_arn

  rotation_rules {
    automatically_after_days = 30
  }
}

resource "aws_ssm_parameter" "db" {
  for_each = var.rds_enabled ? {
    db-host       = local.db_host
    db-secret-arn = local.db_secret_arn
  } : {}

  name  = "/tms/app/config/${each.key}"
  type  = "String"
  value = each.value
}
