# `modules/bedrock-agentcore`

Wraps the official [`aws-ia/agentcore/aws`](https://registry.terraform.io/modules/aws-ia/agentcore/aws/latest)
module (pinned to `0.0.2`) to provision an Amazon Bedrock AgentCore
Runtime + Memory + Gateway triple in a VPC.

## Requirements

- `hashicorp/aws ~> 6.21` (`aws_bedrockagentcore_*` resource types).
- An ARM64 OCI image at `var.runtime_image_uri`. Build with
  `docker buildx --platform=linux/arm64` and push to the per-account
  ECR repo from `infrastructure/modules/ecr-repositories`.
- Bedrock model access enabled in the account/region (console-only;
  see `aqp_docs/docs/how-to/operations/aws-deploy.md`).

## Wiring contract

| SSM parameter                                    | Purpose                                              |
| ------------------------------------------------ | ---------------------------------------------------- |
| `/aqp/${env}/agentcore_runtime_arn`              | Read by `aqp.agents.runtime.AgentRuntime.delegated`. |
| `/aqp/${env}/agentcore_gateway_arn`              | Read by `aqp.agents.tools.bedrock_agentcore_gateway`.|
| `/aqp/${env}/agentcore_memory_id`                | Read by `aqp.agents.runtime.AgentRuntime.delegated`. |
| `/aqp/${env}/agentcore_runtime_policy_arn`       | Attached to the runtime role by the composition.     |
