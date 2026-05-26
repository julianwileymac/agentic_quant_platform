# `modules/bedrock-kb-sync-lambda`

Lazy re-ingestion glue for the Bedrock Knowledge Base. Provisions a
Python Lambda that calls `bedrock-agent:StartIngestionJob` when
EventBridge delivers an `Object Created` event for the KB source bucket.

## Pairing

Always compose with `modules/eventbridge-stepfunctions` — pass
`module.kb_sync.lambda_arn` into the latter's `kb_sync_lambda_arn`
input, and the matching source bucket name into its
`kb_source_bucket_name` input.

## IAM scope

Least-privilege:

- `bedrock-agent:StartIngestionJob` on the specific KB + data source ARNs.
- `s3:Get*` / `ListBucket` on the source bucket only.
- `logs:Put*` on its own log group.

No other Bedrock action is granted; no other S3 bucket is reachable.

## Idempotency

Bedrock KB coalesces concurrent ingestion jobs per KB. The handler
swallows `ConflictException` (a job is already running) and
`ThrottlingException` (rate-limit) so spam from rapid uploads does
not surface as Lambda failures.

## Wiring contract

| SSM parameter                            | Purpose                                    |
| ---------------------------------------- | ------------------------------------------ |
| `/aqp/${env}/kb_sync_lambda_arn`         | EventBridge target ARN (consumed by SFN module) |
