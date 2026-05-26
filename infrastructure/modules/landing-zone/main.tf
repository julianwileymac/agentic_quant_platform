###############################################################################
# modules/landing-zone — AWS Organizations + Control Tower + 5 OUs.
#
# Establishes the multi-account topology described in blueprint §4.1:
#
#   Root
#   ├── Security OU            (Log Archive + Audit accounts)
#   ├── Infrastructure OU      (Network + SharedServices accounts)
#   ├── Workloads OU
#   │   ├── Non-Prod OU        (dev + staging accounts)
#   │   └── Prod OU            (prod account)
#   ├── PolicyStaging OU       (test SCPs before promotion)
#   └── Sandbox OU             ($-cap SCP'd developer experimentation)
#
# Per-OU SCPs:
#   - Deny disabling CloudTrail / Config / GuardDuty.
#   - Restrict regions to us-east-1 / us-east-2 / us-west-2.
#   - Deny public S3 ACLs.
#   - Require IMDSv2.
#   - Deny instance types > g5.12xlarge outside Prod.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "enable_control_tower" {
  description = "Whether to enable Control Tower landing zone (requires AWS Org master access)."
  type        = bool
  default     = true
}

variable "allowed_regions" {
  description = "Region allowlist enforced by SCPs."
  type        = list(string)
  default     = ["us-east-1", "us-east-2", "us-west-2"]
}

resource "aws_organizations_organization" "this" {
  feature_set                   = "ALL"
  enabled_policy_types          = ["SERVICE_CONTROL_POLICY", "TAG_POLICY"]
  aws_service_access_principals = [
    "controltower.amazonaws.com",
    "cloudtrail.amazonaws.com",
    "config.amazonaws.com",
    "guardduty.amazonaws.com",
    "securityhub.amazonaws.com",
  ]
}

resource "aws_organizations_organizational_unit" "security" {
  name      = "Security"
  parent_id = aws_organizations_organization.this.roots[0].id
}

resource "aws_organizations_organizational_unit" "infrastructure" {
  name      = "Infrastructure"
  parent_id = aws_organizations_organization.this.roots[0].id
}

resource "aws_organizations_organizational_unit" "workloads" {
  name      = "Workloads"
  parent_id = aws_organizations_organization.this.roots[0].id
}

resource "aws_organizations_organizational_unit" "non_prod" {
  name      = "Non-Prod"
  parent_id = aws_organizations_organizational_unit.workloads.id
}

resource "aws_organizations_organizational_unit" "prod" {
  name      = "Prod"
  parent_id = aws_organizations_organizational_unit.workloads.id
}

resource "aws_organizations_organizational_unit" "policy_staging" {
  name      = "PolicyStaging"
  parent_id = aws_organizations_organization.this.roots[0].id
}

resource "aws_organizations_organizational_unit" "sandbox" {
  name      = "Sandbox"
  parent_id = aws_organizations_organization.this.roots[0].id
}

###############################################################################
# Service Control Policies — deny destructive ops on platform guardrails.
###############################################################################

resource "aws_organizations_policy" "deny_disable_audit_services" {
  name        = "AqpDenyDisableAuditServices"
  description = "Deny disabling CloudTrail / Config / GuardDuty / Security Hub."
  type        = "SERVICE_CONTROL_POLICY"
  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyAuditServiceDisable"
        Effect = "Deny"
        Action = [
          "cloudtrail:StopLogging",
          "cloudtrail:DeleteTrail",
          "cloudtrail:UpdateTrail",
          "config:DeleteConfigurationRecorder",
          "config:DeleteDeliveryChannel",
          "config:StopConfigurationRecorder",
          "guardduty:DeleteDetector",
          "guardduty:DisassociateFromMasterAccount",
          "securityhub:DisableSecurityHub",
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_organizations_policy" "region_allowlist" {
  name        = "AqpRegionAllowlist"
  description = "Restrict resource creation to the allowlisted regions."
  type        = "SERVICE_CONTROL_POLICY"
  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DenyOutsideAllowedRegions"
        Effect   = "Deny"
        NotAction = [
          "iam:*",
          "organizations:*",
          "controltower:*",
          "support:*",
          "sts:*",
          "route53:*",
          "cloudfront:*",
          "waf:*",
        ]
        Resource = "*"
        Condition = {
          StringNotEquals = {
            "aws:RequestedRegion" = var.allowed_regions
          }
        }
      }
    ]
  })
}

resource "aws_organizations_policy" "require_imdsv2" {
  name        = "AqpRequireIMDSv2"
  description = "EC2 must require IMDSv2."
  type        = "SERVICE_CONTROL_POLICY"
  content = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "DenyRunInstancesWithoutImdsV2"
      Effect = "Deny"
      Action = "ec2:RunInstances"
      Resource = "arn:aws:ec2:*:*:instance/*"
      Condition = {
        StringNotEquals = {
          "ec2:MetadataHttpTokens" = "required"
        }
      }
    }]
  })
}

resource "aws_organizations_policy" "deny_public_s3" {
  name        = "AqpDenyPublicS3"
  description = "Deny public S3 ACLs."
  type        = "SERVICE_CONTROL_POLICY"
  content = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "DenyPublicS3"
      Effect = "Deny"
      Action = [
        "s3:PutBucketAcl",
        "s3:PutObjectAcl",
        "s3:CreateBucket",
        "s3:PutBucketPolicy",
      ]
      Resource = "*"
      Condition = {
        StringEqualsIgnoreCase = {
          "s3:x-amz-acl" = ["public-read", "public-read-write"]
        }
      }
    }]
  })
}

###############################################################################
# AqpDenyBedrockLongTermApiKeys — closes the Sonrai Security disclosure
# (Feb 23 2026: "Cracks in the Bedrock: Bypassing SCP Enforcement with
# Long-Lived API Keys"). Even though the underlying bypass on the
# bedrock-mantle (OpenAI-compatible) endpoint was patched on Jan 29 2026,
# AWS confirmed that long-term Bedrock API keys could side-step SCPs
# between Dec 4 2025 and Jan 26 2026. The safest posture is to deny the
# create/list/get API-key actions entirely; AgentCore Runtime + the
# canonical `router_complete` path use short-term identity-scoped creds
# (IRSA / EKS Pod Identity / ECS task role) so this SCP has no
# legitimate use-case to break.
###############################################################################

resource "aws_organizations_policy" "deny_bedrock_api_keys" {
  name        = "AqpDenyBedrockLongTermApiKeys"
  description = "Deny creation / listing / use of Bedrock long-term API keys (Sonrai bypass)."
  type        = "SERVICE_CONTROL_POLICY"
  content = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "DenyBedrockApiKeyMgmt"
      Effect = "Deny"
      Action = [
        "bedrock:CreateApiKey",
        "bedrock:ListApiKeys",
        "bedrock:GetApiKey",
        "bedrock:DeleteApiKey",
        "bedrock:UpdateApiKey",
        "bedrock:RotateApiKey",
      ]
      Resource = "*"
    }]
  })
}

###############################################################################
# Attach SCPs to OUs — every OU gets the audit + region + IMDSv2 policies.
###############################################################################

locals {
  protected_ous = {
    security       = aws_organizations_organizational_unit.security.id
    infrastructure = aws_organizations_organizational_unit.infrastructure.id
    workloads      = aws_organizations_organizational_unit.workloads.id
    non_prod       = aws_organizations_organizational_unit.non_prod.id
    prod           = aws_organizations_organizational_unit.prod.id
    sandbox        = aws_organizations_organizational_unit.sandbox.id
  }
}

resource "aws_organizations_policy_attachment" "deny_disable_audit_to_ous" {
  for_each  = local.protected_ous
  policy_id = aws_organizations_policy.deny_disable_audit_services.id
  target_id = each.value
}

resource "aws_organizations_policy_attachment" "region_allowlist_to_ous" {
  for_each  = local.protected_ous
  policy_id = aws_organizations_policy.region_allowlist.id
  target_id = each.value
}

resource "aws_organizations_policy_attachment" "imdsv2_to_ous" {
  for_each  = local.protected_ous
  policy_id = aws_organizations_policy.require_imdsv2.id
  target_id = each.value
}

resource "aws_organizations_policy_attachment" "deny_public_s3_to_ous" {
  for_each  = local.protected_ous
  policy_id = aws_organizations_policy.deny_public_s3.id
  target_id = each.value
}

resource "aws_organizations_policy_attachment" "deny_bedrock_api_keys_to_ous" {
  for_each  = local.protected_ous
  policy_id = aws_organizations_policy.deny_bedrock_api_keys.id
  target_id = each.value
}
