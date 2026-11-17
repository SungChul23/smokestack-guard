# 배스천: DB와 함께 켜지는 SSH 터널 전용 인스턴스 (research R10)
# 팀원은 공용 키(콘솔에서 만든 키 쌍)로 DBeaver SSH 터널을 쓴다. 키로는 DB 포트 터널만 되고 셸은 열리지 않는다.
# A의 관리 작업은 SSM 세션으로 한다.

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bastion" {
  name               = "tms-bastion"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "bastion_ssm" {
  role       = aws_iam_role.bastion.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "bastion" {
  name = "tms-bastion"
  role = aws_iam_role.bastion.name
}

resource "aws_instance" "bastion" {
  count = var.rds_enabled ? 1 : 0

  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = var.bastion_instance_type
  key_name                    = var.bastion_key_name
  subnet_id                   = data.aws_subnet.this["public-a"].id
  vpc_security_group_ids      = [data.aws_security_group.this["bastion"].id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.bastion.name

  user_data = templatefile("${path.module}/bastion-user-data.sh", {
    db_host = local.db_host
  })
  user_data_replace_on_change = true

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
    encrypted   = true
  }

  tags = { Name = "tms-bastion" }

  lifecycle {
    ignore_changes = [ami]
  }
}

# 배스천이 새로 만들어져 IP가 바뀌어도 DBeaver 설정은 그대로 두도록 고정 이름을 붙인다.
resource "aws_route53_record" "bastion" {
  count = var.rds_enabled ? 1 : 0

  zone_id = data.aws_route53_zone.main.zone_id
  name    = "bastion.${var.domain_name}"
  type    = "A"
  ttl     = 60
  records = [aws_instance.bastion[0].public_ip]
}
