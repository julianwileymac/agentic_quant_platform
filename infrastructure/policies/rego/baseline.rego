# AQP baseline Terraform plan policies.
#
# Evaluated by ``conftest test`` in
# ``.github/workflows/terraform-pipeline.yml`` against the ``tfplan``
# produced by ``terraform plan -out=tfplan && terraform show -json``.
# A non-empty ``deny`` set fails the PR.
#
# Policies enforced here are the minimum set every workload account
# MUST honour. Per-environment exceptions go in
# ``infrastructure/policies/rego/exceptions_<env>.rego``.

package main

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Helpful aliases for readability.
resource_changes := input.resource_changes

# ---------------------------------------------------------------------------
# Public S3 ACLs — never allowed.
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_s3_bucket"
	some action in change.change.actions
	action != "delete"
	change.change.after.acl == acl
	acl in {"public-read", "public-read-write"}
	msg := sprintf("public S3 ACL not permitted on %s (acl=%s)", [change.address, acl])
}

deny contains msg if {
	some change in resource_changes
	change.type == "aws_s3_bucket_public_access_block"
	some action in change.change.actions
	action != "delete"
	some field in {"block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"}
	change.change.after[field] == false
	msg := sprintf("public access block disabled on %s (%s=false)", [change.address, field])
}

# ---------------------------------------------------------------------------
# Unencrypted EBS volumes — never allowed.
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_ebs_volume"
	some action in change.change.actions
	action != "delete"
	change.change.after.encrypted == false
	msg := sprintf("EBS volume %s must be encrypted", [change.address])
}

# ---------------------------------------------------------------------------
# RDS instances — encryption + backups required.
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_db_instance"
	some action in change.change.actions
	action != "delete"
	change.change.after.storage_encrypted == false
	msg := sprintf("RDS instance %s must set storage_encrypted=true", [change.address])
}

deny contains msg if {
	some change in resource_changes
	change.type == "aws_db_instance"
	some action in change.change.actions
	action != "delete"
	change.change.after.backup_retention_period < 1
	msg := sprintf("RDS instance %s must set backup_retention_period >= 1", [change.address])
}

# ---------------------------------------------------------------------------
# Secrets Manager — at-rest encryption (CMK) required.
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_secretsmanager_secret"
	some action in change.change.actions
	action != "delete"
	not change.change.after.kms_key_id
	msg := sprintf("Secret %s must reference a customer-managed KMS key", [change.address])
}

# ---------------------------------------------------------------------------
# IAM — no wildcard Principal *.
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type in {"aws_iam_role", "aws_iam_role_policy"}
	some action in change.change.actions
	action != "delete"
	policy_doc := change.change.after.assume_role_policy
	is_string(policy_doc)
	contains(policy_doc, "\"Principal\": \"*\"")
	msg := sprintf("IAM role %s has wildcard Principal=*", [change.address])
}

# ---------------------------------------------------------------------------
# ECR — image_tag_mutability must be IMMUTABLE.
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_ecr_repository"
	some action in change.change.actions
	action != "delete"
	change.change.after.image_tag_mutability != "IMMUTABLE"
	msg := sprintf("ECR repo %s must set image_tag_mutability=IMMUTABLE", [change.address])
}

# ---------------------------------------------------------------------------
# Bedrock — never allow ``InvokeModel`` on ``*`` (force allow-list).
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_iam_policy"
	some action in change.change.actions
	action != "delete"
	policy_doc := change.change.after.policy
	is_string(policy_doc)
	contains(policy_doc, "bedrock:InvokeModel")
	contains(policy_doc, "\"Resource\": \"*\"")
	msg := sprintf("IAM policy %s grants bedrock:InvokeModel on '*' — pin to specific FM ARNs", [change.address])
}

# ---------------------------------------------------------------------------
# CloudFront — TLS minimum protocol version must be 1.2+.
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_cloudfront_distribution"
	some action in change.change.actions
	action != "delete"
	change.change.after.viewer_certificate[_].minimum_protocol_version == bad
	bad in {"SSLv3", "TLSv1", "TLSv1_2016", "TLSv1.1_2016"}
	msg := sprintf("CloudFront distribution %s must use TLSv1.2 or higher", [change.address])
}

# ---------------------------------------------------------------------------
# CloudWatch Logs — never disable retention (NEVER_EXPIRE costs unbounded $).
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_cloudwatch_log_group"
	some action in change.change.actions
	action != "delete"
	not change.change.after.retention_in_days
	msg := sprintf("CloudWatch log group %s must set retention_in_days (NEVER_EXPIRE forbidden)", [change.address])
}
