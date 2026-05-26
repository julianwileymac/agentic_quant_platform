###############################################################################
# modules/opensearch-serverless — VECTORSEARCH collection for the Bedrock KB.
#
# Wraps ``aws-ia/opensearch-serverless/aws ~> 0.0.5`` (the Registry pin) so
# the same encryption / network / data-access policies are emitted whether
# we instantiate it from ``modules/bedrock-knowledge-base`` or directly.
#
# Eventual-consistency guard (per avangards.io): the IAM
# ``aoss:APIAccessAll`` permission takes ~20s to propagate. The consumer
# composition that wires Bedrock KB onto this collection MUST insert a
# matching ``time_sleep`` between the IAM grant and the KB resource; this
# module exports the collection ARN so the consumer can express the
# dependency cleanly.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws  = { source = "hashicorp/aws", version = "~> 5.70" }
    time = { source = "hashicorp/time", version = "~> 0.12" }
  }
}

module "collection" {
  source  = "aws-ia/opensearch-serverless/aws"
  version = "~> 0.0.5"

  collection_name = "${var.name_prefix}-${var.collection_suffix}-${var.environment}"
  collection_type = "VECTORSEARCH"

  # VPC-only — the KB ingestion job reaches the collection through the
  # VPC interface endpoint the consumer composition wires alongside.
  network_policy_public_dashboard  = var.public_dashboard
  network_policy_public_collection = var.public_collection
  encryption_policy_kms_key_arn    = var.kms_key_arn
}

###############################################################################
# Optional 20s post-grant settle — consumers can depend_on this resource
# instead of writing their own time_sleep block when they grant
# ``aoss:APIAccessAll`` immediately before creating the KB.
###############################################################################

resource "time_sleep" "settle" {
  depends_on      = [module.collection]
  create_duration = var.settle_duration
}

resource "aws_ssm_parameter" "collection_arn" {
  name  = "/aqp/${var.environment}/kb_collection_arn"
  type  = "String"
  value = module.collection.collection_arn
  tags  = var.tags
}

resource "aws_ssm_parameter" "collection_name" {
  name  = "/aqp/${var.environment}/kb_collection_name"
  type  = "String"
  value = module.collection.collection_name
  tags  = var.tags
}
