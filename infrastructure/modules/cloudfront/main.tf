###############################################################################
# modules/cloudfront — CloudFront distribution in front of the ALB.
#
# Edge layer for the AWS-native admin + AgentCore surfaces only. The
# public marketing site at ``aqp.fund`` stays on Cloudflare (current
# canonical edge per the cloudflare-edge rule); CloudFront here serves
# ``admin.aqp.fund`` + ``agentcore.aqp.fund``.
#
# Notable settings:
#  - Origin = ALB (HTTP — TLS terminates at the edge, ALB-side TLS on
#    the public listener is still required for end-to-end encryption).
#  - WAFv2 association via the operator-supplied web ACL ARN (a real
#    distribution always pins a managed AWS rules set + the
#    AWSManagedRulesCommonRuleSet + AWSManagedRulesKnownBadInputsRuleSet).
#  - Custom cache-control behaviour:
#       * /_internal/*  — never cached
#       * /agentcore/*  — never cached (streaming WS)
#       * /assets/*     — cached aggressively (immutable SPA bundles)
#  - Access logs land in the operator-supplied S3 bucket (replicated to
#    the log-archive account).
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

resource "aws_cloudfront_function" "security_headers" {
  name    = "${var.name_prefix}-sec-headers-${var.environment}"
  runtime = "cloudfront-js-1.0"
  comment = "Inject security headers (HSTS, X-Content-Type-Options, etc.)."
  publish = true

  code = <<-JS
    function handler(event) {
      var response = event.response;
      var headers = response.headers;
      headers['strict-transport-security'] = { value: 'max-age=63072000; includeSubDomains; preload' };
      headers['x-content-type-options']   = { value: 'nosniff' };
      headers['x-frame-options']          = { value: 'DENY' };
      headers['referrer-policy']          = { value: 'no-referrer' };
      headers['content-security-policy']  = { value: "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' https:; frame-ancestors 'none'" };
      return response;
    }
  JS
}

resource "aws_cloudfront_distribution" "this" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.name_prefix} ${var.environment} — AWS-native admin/AgentCore edge."
  aliases         = var.aliases
  price_class     = var.price_class
  http_version    = "http2and3"
  web_acl_id      = var.waf_web_acl_arn

  origin {
    origin_id                = "alb-${var.name_prefix}-${var.environment}"
    domain_name              = var.alb_dns_name
    connection_attempts      = 3
    connection_timeout       = 10

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = "X-CloudFront-Secret"
      value = var.origin_secret_header_value
    }
  }

  default_cache_behavior {
    target_origin_id       = "alb-${var.name_prefix}-${var.environment}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id

    function_association {
      event_type   = "viewer-response"
      function_arn = aws_cloudfront_function.security_headers.arn
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    target_origin_id       = "alb-${var.name_prefix}-${var.environment}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id = data.aws_cloudfront_cache_policy.caching_optimized.id

    function_association {
      event_type   = "viewer-response"
      function_arn = aws_cloudfront_function.security_headers.arn
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/agentcore/*"
    target_origin_id       = "alb-${var.name_prefix}-${var.environment}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = false

    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    minimum_protocol_version = "TLSv1.2_2021"
    ssl_support_method       = "sni-only"
  }

  restrictions {
    geo_restriction {
      restriction_type = var.geo_restriction_type
      locations        = var.geo_restriction_locations
    }
  }

  dynamic "logging_config" {
    for_each = var.access_logs_bucket_domain != null ? [1] : []
    content {
      bucket          = var.access_logs_bucket_domain
      prefix          = "${var.name_prefix}-cf-${var.environment}/"
      include_cookies = false
    }
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-cf-${var.environment}" })
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

resource "aws_ssm_parameter" "distribution_domain" {
  name  = "/aqp/${var.environment}/cloudfront_domain"
  type  = "String"
  value = aws_cloudfront_distribution.this.domain_name
  tags  = var.tags
}

resource "aws_ssm_parameter" "distribution_id" {
  name  = "/aqp/${var.environment}/cloudfront_distribution_id"
  type  = "String"
  value = aws_cloudfront_distribution.this.id
  tags  = var.tags
}
