# `modules/opensearch-serverless`

Wraps [`aws-ia/opensearch-serverless/aws ~> 0.0.5`](https://registry.terraform.io/modules/aws-ia/opensearch-serverless/aws/latest)
to provision a private VECTORSEARCH collection for the Bedrock
Knowledge Base.

## Eventual-consistency guard

`aoss:APIAccessAll` takes ~20 s to propagate after the IAM grant. The
module exports `time_sleep.settle.id` — consumers (typically
`modules/bedrock-knowledge-base`) `depends_on = [time_sleep.settle]`
to wait out the race before issuing their first ingestion job.

## Wiring contract

| SSM parameter                                  |
| ---------------------------------------------- |
| `/aqp/${env}/kb_collection_arn`                |
| `/aqp/${env}/kb_collection_name`               |
