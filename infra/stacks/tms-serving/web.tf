# 화면: 비공개 S3 + CloudFront(OAC) + 루트·www 레코드 (research R7)
# 화면 파일은 별도 저장소 smokestack-guard-web-v2의 deploy 워크플로가 올린다(#94). Terraform은 빈 버킷만 만든다.

resource "aws_s3_bucket" "web" {
  bucket = var.web_bucket_name
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket = aws_s3_bucket.web.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "web" {
  bucket = aws_s3_bucket.web.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "tms-web"
  description                       = "smokestack-guard web bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# 원본의 Cache-Control을 따른다: 해시 파일은 1년, index.html은 no-cache(CI가 붙임)
resource "aws_cloudfront_cache_policy" "web" {
  name        = "tms-web-origin-headers"
  comment     = "Honor origin Cache-Control"
  min_ttl     = 0
  default_ttl = 86400
  max_ttl     = 31536000

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true

    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

# www → 루트 301
resource "aws_cloudfront_function" "www_redirect" {
  name    = "tms-www-redirect"
  runtime = "cloudfront-js-2.0"
  comment = "Redirect www to apex"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var req = event.request;
      var host = req.headers.host && req.headers.host.value;
      if (host && host.indexOf('www.') === 0) {
        return {
          statusCode: 301,
          statusDescription: 'Moved Permanently',
          headers: { location: { value: 'https://${var.domain_name}' + req.uri } }
        };
      }
      return req;
    }
  EOT
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "smokestack-guard web"
  aliases             = [var.domain_name, "www.${var.domain_name}"]
  default_root_object = "index.html"
  price_class         = "PriceClass_200"
  http_version        = "http2and3"

  origin {
    origin_id                = "web-s3"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  default_cache_behavior {
    target_origin_id       = "web-s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = aws_cloudfront_cache_policy.web.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.www_redirect.arn
    }
  }

  # 화면 안 경로(/stacks/123)로 새로고침해도 index.html을 준다. 비공개 버킷은 없는 키에 403을 준다.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.web.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

data "aws_iam_policy_document" "web_bucket" {
  statement {
    sid       = "CloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.web.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = data.aws_iam_policy_document.web_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.web]
}

resource "aws_route53_record" "web" {
  for_each = toset(flatten([
    for name in [var.domain_name, "www.${var.domain_name}"] : [
      for type in ["A", "AAAA"] : "${name}|${type}"
    ]
  ]))

  zone_id = data.aws_route53_zone.main.zone_id
  name    = split("|", each.value)[0]
  type    = split("|", each.value)[1]

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_ssm_parameter" "web" {
  for_each = {
    web-bucket          = aws_s3_bucket.web.id
    web-distribution-id = aws_cloudfront_distribution.web.id
  }

  name  = "/tms/app/config/${each.key}"
  type  = "String"
  value = each.value
}
