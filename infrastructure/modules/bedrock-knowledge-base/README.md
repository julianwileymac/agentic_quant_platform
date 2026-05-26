# `modules/bedrock-knowledge-base`

Wraps [`aws-ia/bedrock/aws`](https://registry.terraform.io/modules/aws-ia/bedrock/aws/latest)
with `kb_storage_type = "OPENSEARCH_SERVERLESS"` so the KB writes vector
chunks into the upstream `modules/opensearch-serverless` collection.

## Pairing

Always compose with `modules/opensearch-serverless` first; pass the
collection ARN + name + `settle_resource_id` so the eventual-consistency
guard (`aoss:APIAccessAll` propagation ~20s) doesn't bite the first
plan/apply.

## Wiring contract

| SSM parameter                                | Purpose                                         |
| -------------------------------------------- | ----------------------------------------------- |
| `/aqp/${env}/kb_knowledge_base_id`           | Bedrock KB id — used by the KB sync Lambda.     |
| `/aqp/${env}/kb_source_bucket`               | Operator-owned S3 bucket (research docs land here).|
