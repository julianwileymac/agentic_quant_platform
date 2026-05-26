# `envs/minimum`

Single-account, lowest-cost AQP infrastructure tier. ~$140/month fixed
+ Bedrock token spend. See
[aqp_docs/docs/how-to/operations/aws-deploy.md](../../../aqp_docs/docs/how-to/operations/aws-deploy.md)
for the end-to-end runbook.

## What this provisions

- VPC (2 AZs, **single NAT** to save ~$32/mo)
- ECR (3 repos: `aqp-admin`, `aqp-admin-frontend`, `aqp-core`)
- RDS Postgres 16 (`db.t4g.medium`, single-AZ)
- ElastiCache Redis 7 (`cache.t4g.small`, 1 node, AUTH token in
  Secrets Manager)
- IAM policy granting Bedrock InvokeModel on Claude Haiku 4.5 only
- GitHub Actions deployer role (`AqpGithubDeployerMinimum`)
- SSM `/aqp/minimum/*` publishes so the application tier
  ([aqp_platform/terraform/environments/minimum](../../../aqp_platform/terraform/environments/minimum))
  can read every handle without remote-state.

## What this deliberately SKIPS

- AWS Organization / Control Tower / SCPs (single-account = nothing to attach)
- EKS + Karpenter + ArgoCD (no quant runtime tier; use ECS Fargate)
- MSK Kafka (no streaming for v1)
- `observability-stack` Helm release (CloudWatch + the ADOT sidecar
  from `aqp_platform/deployments/kubernetes/observability/adot-sidecar/`
  is enough)
- `eso-bootstrap` (Fargate task role reads Secrets Manager via SDK)
- Bedrock AgentCore Runtime / KB / OpenSearch (just use the Bedrock
  LLM provider — Phase D)
- CloudFront + EventBridge SFN

## Quick start

```bash
# 1. Bootstrap state backend (one-time):
cd ../../bootstrap
terraform init && terraform apply -auto-approve
terraform output -json > /tmp/bootstrap.json

# 2. Render backend.hcl + terraform.tfvars:
cd ../envs/minimum
sed "s/<account-id>/$(jq -r '.account_id.value' /tmp/bootstrap.json)/" \
  backend.hcl.example > backend.hcl
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with the bootstrap output values.

# 3. Apply:
terraform init -backend-config=backend.hcl
terraform apply
```

## Promote to the full topology

When you outgrow the minimum, the same SSM parameters are read by
both `infrastructure/envs/{dev,staging,prod}` and the full
`aqp_platform/terraform/environments/live`. Add modules one at a time
— the SSM-parameter contract means no application-side change is
required to introduce CloudFront / AgentCore / EKS later.
