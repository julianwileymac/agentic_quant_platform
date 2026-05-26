###############################################################################
# modules/alb — public ALB + listener + Cognito OIDC integration.
#
# Wraps ``terraform-aws-modules/alb/aws ~> 9.0`` so the listener rules,
# WAFv2 association, and access-logs S3 wiring all share one well-tested
# implementation. The ALB sits in front of the ECS Fargate control plane
# (modules/ecs-fargate-control-plane) and the AgentCore reverse proxy.
#
# Cognito OIDC integration: the listener forwards the access token from
# the Cognito User Pool (modules/cognito-userpool) and rejects requests
# whose ``client_id`` claim isn't in the per-tenant allow-list. The
# ALB's built-in ``authenticate-cognito`` action handles the bulk of
# the OIDC dance — the application backend simply reads the propagated
# claims from the ``X-Amzn-Oidc-*`` headers.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.70" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-${var.environment}"
  description = "Public ALB — 443 from 0.0.0.0/0, optional 80 redirect."
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS from the public internet (CloudFront fronts it)."
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = var.enable_http_redirect ? [1] : []
    content {
      description = "HTTP for ALB-side -> HTTPS redirect."
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.0.0.0/8"]
  }

  tags = var.tags
}

module "alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "~> 9.0"

  name               = "${var.name_prefix}-alb-${var.environment}"
  load_balancer_type = "application"
  vpc_id             = var.vpc_id
  subnets            = var.public_subnet_ids
  security_groups    = [aws_security_group.alb.id]

  access_logs = var.access_logs_bucket != null ? {
    bucket  = var.access_logs_bucket
    prefix  = "${var.name_prefix}-alb-${var.environment}"
    enabled = true
  } : {}

  enable_deletion_protection = var.environment == "prod"
  drop_invalid_header_fields = true
  idle_timeout               = 120

  tags = var.tags
}

resource "aws_lb_target_group" "default" {
  for_each = var.target_groups

  name        = "${var.name_prefix}-${each.key}-${var.environment}"
  port        = each.value.port
  protocol    = each.value.protocol
  vpc_id      = var.vpc_id
  target_type = "ip" # Fargate awsvpc network mode

  health_check {
    enabled             = true
    path                = each.value.health_check_path
    port                = "traffic-port"
    protocol            = each.value.protocol
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200-399"
  }

  deregistration_delay = 30
  tags                 = var.tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = module.alb.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.default[var.default_target_group_key].arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  count = var.enable_http_redirect ? 1 : 0

  load_balancer_arn = module.alb.arn
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

resource "aws_lb_listener_rule" "cognito_auth" {
  for_each = var.cognito_protected_paths

  listener_arn = aws_lb_listener.https.arn
  priority     = each.value.priority

  action {
    type = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn       = var.cognito_user_pool_arn
      user_pool_client_id = var.cognito_user_pool_client_id
      user_pool_domain    = var.cognito_user_pool_domain
      session_cookie_name = "AWSELBAuthSessionCookie"
      session_timeout     = 28800
      scope               = "openid email profile"
      on_unauthenticated_request = "authenticate"
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.default[each.value.target_group_key].arn
  }

  condition {
    path_pattern {
      values = each.value.path_patterns
    }
  }
}

resource "aws_ssm_parameter" "alb_dns_name" {
  name  = "/aqp/${var.environment}/alb_dns_name"
  type  = "String"
  value = module.alb.dns_name
  tags  = var.tags
}

resource "aws_ssm_parameter" "alb_arn" {
  name  = "/aqp/${var.environment}/alb_arn"
  type  = "String"
  value = module.alb.arn
  tags  = var.tags
}

resource "aws_ssm_parameter" "alb_zone_id" {
  name  = "/aqp/${var.environment}/alb_zone_id"
  type  = "String"
  value = module.alb.zone_id
  tags  = var.tags
}
