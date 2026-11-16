# 서비스 네트워크 (specs/a-platform/009-service-infra/data-model.md §2, research R3)
# AZ 2개 × 퍼블릭·앱·DB 서브넷. NAT는 변수로 0~2개.

locals {
  azs = {
    a = "ap-northeast-2a"
    c = "ap-northeast-2c"
  }

  subnets = {
    public-a = { az = "a", cidr = "10.20.0.0/24", tier = "public" }
    public-c = { az = "c", cidr = "10.20.1.0/24", tier = "public" }
    app-a    = { az = "a", cidr = "10.20.10.0/24", tier = "app" }
    app-c    = { az = "c", cidr = "10.20.11.0/24", tier = "app" }
    db-a     = { az = "a", cidr = "10.20.20.0/24", tier = "db" }
    db-c     = { az = "c", cidr = "10.20.21.0/24", tier = "db" }
  }

  # NAT가 1개면 두 AZ가 AZ-a NAT를 같이 쓴다.
  nat_for_az = {
    a = 0
    c = var.nat_gateway_count >= 2 ? 1 : 0
  }
}

resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "tms-vpc" }
}

resource "aws_subnet" "this" {
  for_each = local.subnets

  vpc_id                  = aws_vpc.main.id
  availability_zone       = local.azs[each.value.az]
  cidr_block              = each.value.cidr
  map_public_ip_on_launch = each.value.tier == "public"

  tags = {
    Name     = "tms-${each.key}"
    tms_tier = each.value.tier
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "tms-igw" }
}

# ── 퍼블릭 ──
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "tms-public" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  for_each = { for k, v in local.subnets : k => v if v.tier == "public" }

  subnet_id      = aws_subnet.this[each.key].id
  route_table_id = aws_route_table.public.id
}

# ── NAT (변수) ──
resource "aws_eip" "nat" {
  count  = var.nat_gateway_count
  domain = "vpc"
  tags   = { Name = "tms-nat-${keys(local.azs)[count.index]}" }
}

resource "aws_nat_gateway" "this" {
  count = var.nat_gateway_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.this["public-${keys(local.azs)[count.index]}"].id
  tags          = { Name = "tms-nat-${keys(local.azs)[count.index]}" }

  depends_on = [aws_internet_gateway.main]
}

# ── 앱 (AZ마다 라우팅 테이블) ──
resource "aws_route_table" "app" {
  for_each = local.azs

  vpc_id = aws_vpc.main.id
  tags   = { Name = "tms-app-${each.key}" }
}

resource "aws_route" "app_nat" {
  for_each = var.nat_gateway_count > 0 ? local.azs : {}

  route_table_id         = aws_route_table.app[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[local.nat_for_az[each.key]].id
}

resource "aws_route_table_association" "app" {
  for_each = local.azs

  subnet_id      = aws_subnet.this["app-${each.key}"].id
  route_table_id = aws_route_table.app[each.key].id
}

# ── DB (밖으로 나가는 경로 없음) ──
resource "aws_route_table" "db" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "tms-db" }
}

resource "aws_route_table_association" "db" {
  for_each = local.azs

  subnet_id      = aws_subnet.this["db-${each.key}"].id
  route_table_id = aws_route_table.db.id
}

# S3는 NAT를 거치지 않는 무료 경로로
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.ap-northeast-2.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat([for rt in aws_route_table.app : rt.id], [aws_route_table.db.id])
  tags              = { Name = "tms-s3" }
}
