# AWS Minimum Tier Rollback Playbook

> Companion to
> [aws-minimum-single-account.md](aws-minimum-single-account.md) (deploy)
> and [aws-runbook.md](aws-runbook.md) (full-stack on-call).
>
> This page is the dedicated rollback procedure for the single-account
> minimum tier deployed via
> [infrastructure/envs/minimum/scripts/deploy.sh](../../../../infrastructure/envs/minimum/scripts/deploy.sh).

## TL;DR — One Command Rollback

```bash
cd infrastructure/envs/minimum
ACCOUNT_ALIAS=minimum AWS_REGION=us-east-1 bash scripts/destroy.sh
```

That command:

1. Checks the caller's AWS account id matches the snapshot from deploy.
2. Destroys the application tier (Cognito + ALB + Fargate).
3. Disables RDS deletion protection.
4. Takes a final RDS snapshot (skip with `DESTROY_RDS_SKIP_SNAPSHOT=yes`).
5. Destroys the infrastructure tier (VPC + RDS + Redis + IAM + alarms).
6. Lists any orphan resources that survived destroy.
7. Retains the bootstrap state backend (S3 + DynamoDB + KMS + OIDC).

Total wall-clock: ~15 minutes (RDS snapshot is the long pole).

## When to Roll Back

| Situation | Action |
| --- | --- |
| Wrong account / region | `bash scripts/destroy.sh` immediately; the identity guard will catch the mismatch before destroying anything. |
| Cost overrun | `bash scripts/destroy.sh` then re-deploy with smaller instance types. |
| Failed apply mid-flight | `bash scripts/destroy.sh` (idempotent — resumes from wherever apply stopped). |
| Need clean slate | `DESTROY_BOOTSTRAP=yes bash scripts/destroy.sh` (also nukes the state backend). |
| RDS data corruption | `DESTROY_RDS_SKIP_SNAPSHOT=yes bash scripts/destroy.sh` (skip the bad-data snapshot). |
| Security incident | See [aws-runbook.md](aws-runbook.md) §"Halt every AgentCore session" first; THEN consider destroy. |

## Pre-Rollback Checklist

Before running `destroy.sh`:

- [ ] **Confirm there's no critical data** in RDS that hasn't been backed up
      out-of-band. The default rollback takes a final snapshot, but if you
      pass `DESTROY_RDS_SKIP_SNAPSHOT=yes`, data is gone.
- [ ] **Confirm no other team / env is using the bootstrap state backend.**
      The default `DESTROY_BOOTSTRAP=no` preserves it. Flipping to `yes`
      affects every env that shares the same `aqp-tfstate-<alias>` bucket.
- [ ] **Capture forensics first** for a security incident:
      ```bash
      bash scripts/snapshot.sh capture
      ```
      Then destroy.

## The Six Stages

### Stage 1 — Identity Guard

```bash
# destroy.sh reads .snapshots/latest/deploy-receipt.json and confirms
# the caller's STS identity matches.
# If you see: "deploy receipt is for account 111 but caller is 222"
# → STOP. You're in the wrong account. Switch profiles + retry.
```

The receipt is created by `deploy.sh` Step 8 and stored at
`infrastructure/envs/minimum/.snapshots/<UTC>/deploy-receipt.json`.

### Stage 2 — Application Tier

The app tier holds the runtime contract — destroying it FIRST means
the ALB target groups release their ECS service refs, so the
infrastructure-tier ALB delete doesn't 409 with "still in use".

Manual override if needed:

```bash
cd aqp_platform/terraform/environments/minimum
terraform init -reconfigure -backend-config=backend.hcl
terraform destroy -auto-approve
```

### Stage 3 — RDS Deletion-Protection Bypass

```bash
aws rds modify-db-instance \
  --db-instance-identifier aqp-admin-min \
  --no-deletion-protection --apply-immediately
```

`destroy.sh` does this automatically; the manual command above is the
fallback if the script can't reach RDS for some reason.

### Stage 4 — Infrastructure Tier

```bash
cd infrastructure/envs/minimum
terraform init -reconfigure -backend-config=backend.hcl
terraform destroy -auto-approve
```

Skips the ECR repos by default (they're declared in
`modules/ecr-repositories` with no `prevent_destroy`, so they get
removed — but ECR's lifecycle policy keeps the most recent 30 tagged
images for 14 days even after the repo deletes).

### Stage 5 — Orphan Sweep

If `destroy.sh` reports orphans:

```bash
[DESTROY]   ⚠ found 3 orphan resource(s) — review + hand-delete:
    arn:aws:ec2:us-east-1:123:network-interface/eni-0a1b2c3d
    arn:aws:logs:us-east-1:123:log-group:/aws/ecs/aqp-admin-min
    arn:aws:elasticloadbalancing:us-east-1:123:listener-rule/...
```

Hand-delete each:

```bash
# ENI stuck in 'available' from a deleted ECS task
aws ec2 delete-network-interface --network-interface-id eni-0a1b2c3d

# Log group with retention != never (terraform doesn't auto-delete these)
aws logs delete-log-group --log-group-name /aws/ecs/aqp-admin-min

# Orphan listener rule (rare — usually the ALB destroy covers it)
aws elbv2 delete-rule --rule-arn arn:aws:elasticloadbalancing:...
```

Common orphan sources:

- **NAT-attached EIPs** — the NAT Gateway is gone but the EIP is not
  released automatically.
- **ECS task ENIs** in `available` state — task definition was deleted
  but the ENI lingers until the underlying ENA cleanup runs.
- **CloudWatch log groups with retention != never_expire** — terraform
  doesn't delete them; they linger but cost nothing until they fill up.
- **Listener rules** with a target group that already deleted.

### Stage 6 — Bootstrap (Optional)

Only when `DESTROY_BOOTSTRAP=yes`. The state bucket has Object Lock
GOVERNANCE, so the script empties it with `--bypass-governance-retention`:

```bash
DESTROY_BOOTSTRAP=yes bash scripts/destroy.sh
```

What this destroys:

- S3 state bucket (every version + delete marker)
- DynamoDB lock table
- KMS CMK (30-day deletion window, recoverable until then)
- GitHub OIDC provider

What this does NOT destroy:

- The aws account itself.
- AWS CloudTrail (default trail in the account; AWS bills for it
  regardless).
- The Bedrock model-access grant (console-only setting; persists
  across teardowns).

## Recovery After a Partial Destroy

If `destroy.sh` fails mid-flight:

```bash
# 1. Inspect the .destroy.log for the failed step.
tail -100 infrastructure/envs/minimum/.destroy.log

# 2. Re-run destroy — it's idempotent + resumes from wherever apply stopped.
bash scripts/destroy.sh

# 3. If terraform state is locked, force-unlock:
cd infrastructure/envs/minimum
terraform force-unlock <LOCK_ID>

# 4. If a specific resource is wedged, target it:
terraform destroy -target=module.rds.aws_db_instance.this -auto-approve
```

## Cost Verification

After rollback, verify $0 monthly spend in the AWS console:

- **Cost Explorer** → filter by tag `managed_by=terraform`, `env=minimum`
  → should show $0 in the current period.
- **AWS Budgets** → if the alert was wired pre-rollback, it stays armed
  with `actual_spend=0` for the period.

If non-zero spend persists 24 h after rollback:

- Check for **EBS snapshots** that were created by RDS deletion.
- Check for **CloudWatch metric streams** that may have been wired
  manually (not destroyed by `destroy.sh`).
- Check for **Route 53 hosted zones** — these have a $0.50/mo floor.

## Files Touched

| File | Created by | Destroyed by |
| --- | --- | --- |
| `aqp-tfstate-<alias>` S3 bucket | `deploy.sh` (bootstrap step) | `destroy.sh` only with `DESTROY_BOOTSTRAP=yes` |
| `aqp-tfstate-lock-<alias>` DynamoDB table | bootstrap | same |
| `alias/aqp-tfstate` KMS key | bootstrap | same |
| GitHub OIDC provider | bootstrap | same |
| VPC `aqp-min` + subnets + NAT + endpoints | infrastructure tier | `destroy.sh` step 4 |
| RDS `aqp-admin-min` | infrastructure tier | step 4 (final snapshot retained) |
| ElastiCache `aqp-min-redis` | infrastructure tier | step 4 |
| ECR repos | infrastructure tier | step 4 (image lifecycle policy keeps tags 14d) |
| CloudWatch alarms + dashboard | infrastructure tier | step 4 |
| ALB + Cognito + Fargate cluster | application tier | step 2 |
| `.snapshots/<UTC>/` | `snapshot.sh` | preserved on disk forever (committed in `.gitignore` by default) |
