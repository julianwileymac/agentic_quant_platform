# `environments/minimum`

Application tier for the single-account minimum AQP deployment. Sits
on top of
[infrastructure/envs/minimum](../../../../infrastructure/envs/minimum/).

## Modules composed

- `infrastructure/modules/cognito-userpool` — end-user identity
- `infrastructure/modules/alb` — public HTTPS + Cognito-gated rules
- `infrastructure/modules/ecs-fargate-control-plane` — single
  `aqp-admin` task (no AgentCore proxy, no admin frontend yet)

## Wiring

Every handle the application reads comes from
`/aqp/minimum/*` SSM parameters published by the infrastructure tier.
There is NO `data "terraform_remote_state"` block — the two tiers
stay decoupled.

## Quick start

```bash
# 1. Render backend.hcl + terraform.tfvars:
cp backend.hcl.example backend.hcl
sed -i "s/<account-id>/$(jq -r '.account_id.value' /tmp/bootstrap.json)/" backend.hcl
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with the ACM cert ARN + the image tag your CI
# just published to ECR.

# 2. Apply (after infrastructure/envs/minimum is up):
terraform init -backend-config=backend.hcl
terraform apply
```

## Connect AQP to it

Set the application env vars (via task definition / SSM):

```bash
AQP_LLM_PROVIDER=bedrock
AQP_BEDROCK_REGION=us-east-1
AQP_AUTH_PROVIDER=aws_cognito
AQP_AUTH_OIDC_ISSUER=<cognito_user_pool_endpoint>
AQP_DEPLOY_TARGET=aws
```

The matching DB / Redis endpoints come from
`/aqp/minimum/rds_endpoint` + `/aqp/minimum/redis_primary_endpoint`
(the application reads them on boot via boto3 SSM client).

## Promotion path

1. Add `infrastructure/modules/cloudfront` to point `admin.aqp.fund`
   at the ALB.
2. Add `infrastructure/modules/bedrock-knowledge-base` +
   `opensearch-serverless` when research docs become a thing.
3. Add `infrastructure/modules/bedrock-agentcore` + an `aqp-agent`
   ECS service to migrate from in-process CrewAI to AgentCore.
4. Stand up EKS via `infrastructure/envs/dev` (or a new `eks-add-on`
   env) when you need the Celery worker / Iceberg writer / MLflow tier.
