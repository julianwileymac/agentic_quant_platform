###############################################################################
# modules/cognito-userpool — Cognito User Pool + ALB OIDC integration.
#
# Front-door identity for the ECS Fargate ALB. The pool issues OIDC tokens
# the ALB validates via its built-in Cognito integration; the per-tenant
# app clients (provisioned by the rule-42 tenant-namespace bundle in
# ``aqp_cp.terraform.builders.manifests``) get filtered by ``client_id``
# inside the ALB listener rules so cross-tenant token replay is rejected
# at the edge.
#
# The shared app client is registered here. Per-tenant clients are NOT
# created in this module — that's the tenant-namespace bundle's job
# (one ``aws_cognito_user_pool_client`` per :class:`EntraTenantLink`).
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

resource "aws_cognito_user_pool" "this" {
  name = "${var.name_prefix}-userpool-${var.environment}"

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  mfa_configuration = var.mfa_configuration

  dynamic "software_token_mfa_configuration" {
    for_each = var.mfa_configuration != "OFF" ? [1] : []
    content {
      enabled = true
    }
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = var.invite_only
  }

  auto_verified_attributes = ["email"]

  username_attributes = ["email"]

  schema {
    name                     = "email"
    attribute_data_type      = "String"
    required                 = true
    mutable                  = true
    developer_only_attribute = false
    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  user_pool_add_ons {
    advanced_security_mode = var.advanced_security_mode
  }

  deletion_protection = var.environment == "prod" ? "ACTIVE" : "INACTIVE"

  tags = merge(var.tags, { Name = "${var.name_prefix}-userpool-${var.environment}" })
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = "${var.name_prefix}-${var.environment}-${random_id.domain_suffix.hex}"
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "random_id" "domain_suffix" {
  byte_length = 4
}

resource "aws_cognito_user_pool_client" "shared" {
  name         = "${var.name_prefix}-shared-client-${var.environment}"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret                      = true
  prevent_user_existence_errors        = "ENABLED"
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  access_token_validity                = 60
  id_token_validity                    = 60
  refresh_token_validity               = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_identity_pool" "this" {
  count                            = var.create_identity_pool ? 1 : 0
  identity_pool_name               = "${var.name_prefix}-idpool-${var.environment}"
  allow_unauthenticated_identities = false

  cognito_identity_providers {
    client_id     = aws_cognito_user_pool_client.shared.id
    provider_name = aws_cognito_user_pool.this.endpoint
    server_side_token_check = true
  }

  tags = var.tags
}

###############################################################################
# SSM Parameter Store outputs — consumers (ALB module, tenant-namespace
# bundle, aqp/auth/providers/aws_cognito.py) read these to wire OIDC.
###############################################################################

resource "aws_ssm_parameter" "user_pool_id" {
  name  = "/aqp/${var.environment}/cognito_user_pool_id"
  type  = "String"
  value = aws_cognito_user_pool.this.id
  tags  = var.tags
}

resource "aws_ssm_parameter" "user_pool_arn" {
  name  = "/aqp/${var.environment}/cognito_user_pool_arn"
  type  = "String"
  value = aws_cognito_user_pool.this.arn
  tags  = var.tags
}

resource "aws_ssm_parameter" "user_pool_endpoint" {
  name  = "/aqp/${var.environment}/cognito_user_pool_endpoint"
  type  = "String"
  value = "https://${aws_cognito_user_pool.this.endpoint}"
  tags  = var.tags
}

resource "aws_ssm_parameter" "shared_client_id" {
  name  = "/aqp/${var.environment}/cognito_shared_client_id"
  type  = "String"
  value = aws_cognito_user_pool_client.shared.id
  tags  = var.tags
}

resource "aws_ssm_parameter" "shared_client_secret" {
  name        = "/aqp/${var.environment}/cognito_shared_client_secret"
  type        = "SecureString"
  value       = aws_cognito_user_pool_client.shared.client_secret
  tags        = var.tags
  description = "Cognito SPA client secret — consumed by AwsCognitoProvider."
}

resource "aws_ssm_parameter" "user_pool_domain" {
  name  = "/aqp/${var.environment}/cognito_user_pool_domain"
  type  = "String"
  value = aws_cognito_user_pool_domain.this.domain
  tags  = var.tags
}
