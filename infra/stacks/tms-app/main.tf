# API·에이전트 서버 (research R4·R5). 대수는 변수(기본 0). ALB는 alb.tf, 이미지 저장소는 ecr.tf,
# 서버 권한은 iam.tf, 배포 역할은 deploy_role.tf.

data "aws_caller_identity" "current" {}

data "aws_vpc" "main" {
  tags = { Name = "tms-vpc" }
}

data "aws_subnet" "this" {
  for_each = toset(["public-a", "public-c", "app-a", "app-c"])

  vpc_id = data.aws_vpc.main.id
  tags   = { Name = "tms-${each.key}" }
}

data "aws_security_group" "this" {
  for_each = toset(["alb", "app"])

  vpc_id = data.aws_vpc.main.id
  name   = "tms-${each.key}"
}

# 서버를 켜려면 NAT가 있어야 이미지를 받는다 (아래 ASG precondition)
data "aws_nat_gateways" "available" {
  vpc_id = data.aws_vpc.main.id

  filter {
    name   = "state"
    values = ["available"]
  }
}

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.ap-northeast-2.amazonaws.com"

  apps = {
    api = {
      instance_type = var.api_instance_type
      desired       = var.api_desired
    }
    agent = {
      instance_type = var.agent_instance_type
      desired       = var.agent_desired
    }
  }
}

resource "aws_cloudwatch_log_group" "app" {
  for_each = local.apps

  name              = "/tms/app/${each.key}"
  retention_in_days = 14
}

# "현재 버전" 기록. 배포(main)가 값을 바꾸고 서버가 뜰 때 읽는다. Terraform은 처음 값만 만든다.
resource "aws_ssm_parameter" "image_tag" {
  for_each = local.apps

  name  = "/tms/app/${each.key}/image-tag"
  type  = "String"
  value = "none"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_launch_template" "app" {
  for_each = local.apps

  name                   = "tms-${each.key}"
  image_id               = data.aws_ssm_parameter.al2023.value
  instance_type          = each.value.instance_type
  vpc_security_group_ids = [data.aws_security_group.this["app"].id]
  update_default_version = true

  iam_instance_profile {
    name = aws_iam_instance_profile.app.name
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_type = "gp3"
      volume_size = 20
      encrypted   = true
    }
  }

  user_data = base64encode(templatefile("${path.module}/server-user-data.sh", {
    app      = each.key
    registry = local.registry
    repo     = aws_ecr_repository.app[each.key].name
    origin   = "https://${var.domain_name}"
  }))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name      = "tms-${each.key}"
      "tms:app" = each.key
    }
  }
}

resource "aws_autoscaling_group" "app" {
  for_each = local.apps

  name                = "tms-${each.key}"
  min_size            = each.value.desired
  max_size            = each.value.desired
  desired_capacity    = each.value.desired
  vpc_zone_identifier = [data.aws_subnet.this["app-a"].id, data.aws_subnet.this["app-c"].id]

  # 인스턴스 상태로만 교체한다. 앱이 잠깐 죽거나 이미지가 아직 없을 때 계속 갈아 끼우지 않게 (research R5)
  health_check_type         = "EC2"
  health_check_grace_period = 120
  target_group_arns         = var.alb_enabled ? [aws_lb_target_group.app[each.key].arn] : []

  launch_template {
    id      = aws_launch_template.app[each.key].id
    version = aws_launch_template.app[each.key].latest_version
  }

  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 50
    }
  }

  tag {
    key                 = "tms:app"
    value               = each.key
    propagate_at_launch = true
  }

  lifecycle {
    precondition {
      condition     = each.value.desired == 0 || length(data.aws_nat_gateways.available.ids) > 0
      error_message = "NAT가 없어 서버가 이미지를 받을 수 없다. tms-network에서 nat_gateway_count를 1 이상으로 먼저 적용하라."
    }
  }
}
