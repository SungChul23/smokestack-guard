# https 인증서 2개 (research R7·R14). DNS 검증이라 tms-foundation 영역의 NS 위임이 끝나야 발급된다.

data "aws_route53_zone" "main" {
  name = var.domain_name
}

# CloudFront용: 루트 + www (us-east-1)
resource "aws_acm_certificate" "web" {
  provider = aws.us_east_1

  domain_name               = var.domain_name
  subject_alternative_names = ["www.${var.domain_name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# ALB용: api. (서울)
resource "aws_acm_certificate" "api" {
  domain_name       = "api.${var.domain_name}"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

locals {
  validation_records = merge(
    { for o in aws_acm_certificate.web.domain_validation_options : o.domain_name => o },
    { for o in aws_acm_certificate.api.domain_validation_options : o.domain_name => o },
  )
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.validation_records

  zone_id         = data.aws_route53_zone.main.zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "web" {
  provider = aws.us_east_1

  certificate_arn = aws_acm_certificate.web.arn
  validation_record_fqdns = [
    for d in [var.domain_name, "www.${var.domain_name}"] : aws_route53_record.cert_validation[d].fqdn
  ]
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [aws_route53_record.cert_validation["api.${var.domain_name}"].fqdn]
}
