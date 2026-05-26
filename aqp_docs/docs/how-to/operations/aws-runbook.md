# AWS Hybrid Operational Runbook

> Companion to [aws-deploy.md](aws-deploy.md). Page this when the
> AgentCore proxy / admin BFF / Bedrock KB / ECS Fargate cluster
> misbehaves.

## On-call checklist (first 5 minutes)

1. **Confirm the blast radius.** Cloudflare hosts `aqp.fund` /
   `api.aqp.fund` / `manage.aqp.fund`; CloudFront hosts
   `admin.aqp.fund` / `agentcore.aqp.fund`. A Cloudflare outage does NOT
   touch the admin / AgentCore surface (and vice versa).
2. **Hit `/healthz`.** `https://admin.aqp.fund/healthz` — if 200, the
   ALB + ECS Fargate path is healthy. If 5xx, jump to "ECS Fargate
   service down" below.
3. **Fan-out kill switch.** If the incident is touching trading,
   immediately POST `/portfolio/kill_switch` AND `/workloads/halt` so
   every long-running runtime (paper, bots, RL, AgentCore) stops. The
   topbar `KillSwitch` component does the fan-out automatically for
   logged-in operators.

## Halt every AgentCore session

```bash
# 1. Disable new invocations at the gateway:
aws bedrock-agentcore update-gateway \
  --gateway-id $(aws ssm get-parameter \
    --name /aqp/prod/agentcore_gateway_arn \
    --query 'Parameter.Value' --output text | awk -F/ '{print $NF}') \
  --status DISABLED

# 2. Stop the AgentCore proxy ECS Fargate service (the ALB stops
#    forwarding to the proxy immediately):
aws ecs update-service \
  --cluster $(aws ssm get-parameter \
    --name /aqp/prod/ecs_cluster_name \
    --query 'Parameter.Value' --output text) \
  --service aqp-agentcore-proxy-prod \
  --desired-count 0
```

The matching audit row lands in `workload_runs` via
`WorkloadRuntime.start_run` BEFORE the boto3 call returns (rule 45).
You can verify with:

```bash
aws rds-data execute-statement \
  --resource-arn $RDS_ARN --secret-arn $DB_SECRET_ARN \
  --database aqp \
  --sql "SELECT id, action, status, user_id, started_at \
         FROM workload_runs ORDER BY started_at DESC LIMIT 10"
```

## Roll back to the previous tag

```bash
# 1. Identify the previous good SHA:
git log --oneline --decorate -20

# 2. Tag the previous SHA + push to trigger the apply path:
git tag v1.0.1-rollback <previous-sha>
git push origin v1.0.1-rollback

# 3. Manual dispatch — terraform-pipeline.yml with
#    tree=aqp_platform, env=prod, action=apply (requires 2 reviewers).
#
# The DB / S3 buckets / KB source bucket are NOT touched — every data
# resource carries lifecycle.prevent_destroy=true and retains the
# previous Terraform-managed state.
```

## ECS Fargate service down

```bash
# 1. Inspect recent task stops (most common = ECR pull failure or
#    secrets resolution failure):
aws ecs describe-services \
  --cluster aqp-cluster-prod \
  --services aqp-admin-prod \
  --query 'services[0].events[:10]'

# 2. Tail the application log group (the ADOT sidecar logs to a
#    sibling stream prefixed adot/):
aws logs tail /aws/ecs/aqp-admin-prod --follow

# 3. Force a fresh rollout (also rolls the ADOT sidecar):
aws ecs update-service \
  --cluster aqp-cluster-prod \
  --service aqp-admin-prod \
  --force-new-deployment
```

The matching `AwsProvider.restart` call from `WorkloadRuntime` writes
a `workload_runs` row with `action=restart` BEFORE the boto3 call
runs, so the audit trail is intact even when the rollout fails halfway.

## Drain a Celery worker (EKS path)

The Celery workers continue to run on EKS Karpenter; the ECS Fargate
surface is admin + AgentCore only. To drain a worker pod without
losing in-flight tasks:

```bash
# 1. Annotate the pod for graceful shutdown — the Celery preboot
#    hook in aqp/tasks/celery_app.py listens for this annotation:
kubectl annotate pod aqp-worker-xxxxx \
  -n aqp \
  aqp.io/drain-requested-at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 2. Wait for the worker to finish in-flight tasks (max grace =
#    AQP_AGENT_STALL_THRESHOLD_SECONDS, default 1800s):
kubectl wait --for=delete pod aqp-worker-xxxxx -n aqp --timeout=1900s

# 3. Karpenter replaces the deleted pod automatically; the new pod
#    inherits the same Celery queue subscriptions.
```

## Assume the break-glass role

Reserved for catastrophic incidents (org-wide outage, suspected
account compromise). The `AQP-BreakGlass` Identity Center
permission set has Admin across every account, MFA-required, and
alarms on every assumption (CloudWatch alarm +
`workload_runs` row + Cloudflare Access policy).

```bash
# IAM Identity Center -> Sign in -> Pick AQP-BreakGlass for the
# target account -> Acknowledge the on-call ticket prompt before
# the assume completes.
aws sts get-caller-identity
# Outputs the breakglass session arn — paste into the incident ticket.
```

## Rotate Cloudflare origin secret

When the CloudFront `X-CloudFront-Secret` header value is suspected
leaked:

```bash
new=$(openssl rand -hex 32)

aws ssm put-parameter \
  --name /aqp/prod/cloudfront_origin_secret \
  --value "$new" --type SecureString --overwrite

# Re-apply the cloudfront module so the new value lands at the edge:
gh workflow run terraform-pipeline.yml -f tree=aqp_platform -f env=prod -f action=apply
```

## Common failure modes + fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `AccessDeniedException` on first KB ingestion | `aoss:APIAccessAll` not propagated | Wait 20s + retry (the `time_sleep.settle` block handles this on apply, but manual ingestion-job starts can race). |
| AgentCore Runtime invocation returns 403 | The runtime role's IAM policy denies the FM | Verify the model ARN is in `var.allowed_model_arns` for the env. |
| `terraform apply` fails on `aws_bedrockagentcore_*` resource | Provider version too old | Pin `hashicorp/aws ~> 6.21` in `aqp_platform/terraform/environments/live/main.tf`. |
| ALB 504 on `admin.aqp.fund` | Cognito redirect loop or ALB OIDC misconfig | Inspect the listener rule's `authenticate-cognito` action; confirm `user_pool_arn` + `user_pool_client_id` + `user_pool_domain` SSM params match. |
| ECS exec hangs | Task definition missing `enableExecuteCommand=true` | Re-deploy with `enable_execute_command=true` in the service spec; ECS Exec also needs `AQP_AWS_ECS_EXEC_ENABLED=true` on the provider. |
| Bedrock smoke workflow times out on X-Ray | ADOT sidecar not propagating; check `aqp-adot-sidecar` SA has the X-Ray + Application Signals + CloudWatch policies. | |

## Cost guardrails

`AWS Budgets` alarms ride on top of the SCP region allowlist:

- `dev` budget = $300/month (alerts at 50/80/100%)
- `staging` budget = $500/month
- `prod` budget = $1500/month (excluding Bedrock token spend; that is
  metered separately under the `aqp.io/cost-bucket=bedrock-tokens` tag).

If a budget alarm fires AND the Bedrock token cost is the driver:

```bash
# Disable streaming responses (cheaper) and switch the agent spec to
# Haiku for the next 24h while the operator investigates:
aws ssm put-parameter --name /aqp/prod/llm_model_preference \
  --value "anthropic.claude-haiku-4-5-20251022-v1:0" \
  --type String --overwrite

aws ecs update-service \
  --cluster aqp-cluster-prod \
  --service aqp-agentcore-proxy-prod \
  --force-new-deployment
```
