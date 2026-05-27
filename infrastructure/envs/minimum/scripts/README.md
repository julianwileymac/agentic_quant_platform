# `infrastructure/envs/minimum/scripts/`

Turnkey deploy + rollback bundle for the AQP single-account minimum tier.

## Files

| Script | What it does | Idempotent? |
| --- | --- | --- |
| `preflight.sh` | Read-only sanity check (aws CLI, terraform, region, bedrock model access, state-bucket squat check). | Yes |
| `snapshot.sh` | Captures pre-deploy state (caller identity, pre-existing tagged resources, tfvars, tfstate copies). | Yes — each run gets its own timestamped dir |
| `deploy.sh` | Bootstraps state backend (if missing) + applies the infrastructure tier. | Yes |
| `deploy-app.sh` | Applies the application tier (Cognito + ALB + Fargate) after `deploy.sh` lands. | Yes |
| `destroy.sh` | Reverses everything in the safe order (app → infra → orphan sweep → optional bootstrap). | Yes |

## Operator inputs (env vars)

| Var | Default | Purpose |
| --- | --- | --- |
| `AWS_PROFILE` (or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) | — | Standard AWS credential chain. |
| `AWS_REGION` | `us-east-1` | Target region. Must be one of `us-east-1`, `us-east-2`, `us-west-2` (SCP allowlist). |
| `ACCOUNT_ALIAS` | `minimum` | Bootstrap state bucket suffix (`aqp-tfstate-<alias>`). Lets you stand up multiple isolated tiers in the same account. |
| `DEPLOY_CONFIRM` | _(prompt)_ | Set to `yes` to skip the interactive confirm before `apply`. |
| `DEPLOY_DRY_RUN` | `no` | Run plan only; never apply. |
| `DESTROY_CONFIRM` | _(prompt)_ | Set to `yes` for non-interactive destroy. |
| `DESTROY_DRY_RUN` | `no` | Plan-destroy only; never destroy. |
| `DESTROY_RDS_SKIP_SNAPSHOT` | `no` | Skip the final RDS snapshot (faster + cheaper but data is gone). |
| `DESTROY_BOOTSTRAP` | `no` | Also tear down the bootstrap state backend (S3 + DynamoDB + KMS + OIDC). |
| `ACM_CERT_ARN` | _(prompt)_ | Required by `deploy-app.sh` — regional ACM cert for the ALB HTTPS listener. |
| `ADMIN_IMAGE_TAG` | _(prompt)_ | Required by `deploy-app.sh` — ECR image tag for `aqp-admin`. |

## End-to-end deploy (single account, single command per phase)

```bash
cd infrastructure/envs/minimum

# 1. Read-only preflight (free; ~5 seconds).
ACCOUNT_ALIAS=minimum AWS_REGION=us-east-1 bash scripts/preflight.sh

# 2. Bootstrap state backend + infrastructure tier (interactive confirm).
#    Takes ~12 minutes; RDS provisioning is the long pole.
ACCOUNT_ALIAS=minimum AWS_REGION=us-east-1 bash scripts/deploy.sh

# 3. Push the aqp-admin image. Either via the build-publish.yml workflow
#    OR manually:
#      docker buildx build --platform linux/amd64 \
#        -f aqp_platform/build/docker/aqp-admin/Dockerfile \
#        -t <account>.dkr.ecr.us-east-1.amazonaws.com/aqp-admin:v0.1.0-min \
#        --push ../../..

# 4. Application tier — Cognito + ALB + Fargate.
ACCOUNT_ALIAS=minimum AWS_REGION=us-east-1 \
  ACM_CERT_ARN=arn:aws:acm:us-east-1:123:certificate/abc \
  ADMIN_IMAGE_TAG=v0.1.0-min \
  bash scripts/deploy-app.sh

# 5. Smoke test.
alb=$(cd ../../../aqp_platform/terraform/environments/minimum \
      && terraform output -raw alb_dns_name)
curl -sSI https://${alb}/healthz
```

## Rollback

The destroy script is the canonical rollback. It honors a strict
order so dependencies don't block each other:

1. **Identity guard** — refuses to run if the caller's AWS account id
   doesn't match the snapshot from `deploy.sh`.
2. **Application tier** — Fargate services release ALB target group
   references first, otherwise ALB delete fails.
3. **RDS deletion-protection bypass** — module sets
   `deletion_protection = true`; the script disables it via the AWS
   CLI before terraform reaches the resource. Final snapshot is taken
   by default; set `DESTROY_RDS_SKIP_SNAPSHOT=yes` to skip.
4. **Infrastructure tier** — VPC + RDS + Redis + IAM + alarms.
5. **Orphan sweep** — lists any `managed_by=terraform env=minimum`
   resource that survived destroy (manual cleanup required).
6. **Bootstrap (optional)** — bootstrap state backend stays by default.
   `DESTROY_BOOTSTRAP=yes` empties the Object-Lock'd state bucket +
   nukes the bootstrap stack.

```bash
# Soft rollback — keeps the state backend (most common, ~15 min):
ACCOUNT_ALIAS=minimum AWS_REGION=us-east-1 bash scripts/destroy.sh

# Hard rollback — also remove the bootstrap state backend + OIDC role:
ACCOUNT_ALIAS=minimum AWS_REGION=us-east-1 \
  DESTROY_BOOTSTRAP=yes bash scripts/destroy.sh

# Dry-run anything:
DESTROY_DRY_RUN=yes bash scripts/destroy.sh
```

## Safety properties

- **Account guard** — `destroy.sh` refuses to run if the caller's
  AWS account id doesn't match the snapshot from `deploy.sh`. This
  blocks the "I switched profiles and accidentally destroyed prod"
  failure mode.
- **Region guard** — `preflight.sh` enforces the SCP region allowlist
  (`us-east-1` / `us-east-2` / `us-west-2`).
- **Tag-scoped sweep** — `destroy.sh` only ever touches resources
  tagged `managed_by=terraform env=minimum`. Anything else in the
  account is invisible to it.
- **Snapshot-before-destructive** — every deploy writes a
  `.snapshots/<UTC>/deploy-receipt.json` so a future audit can prove
  who deployed what, when, and where.
- **Bootstrap retention** — the state backend (S3 + DynamoDB + KMS)
  is preserved by default so a follow-up deploy can re-use the same
  storage without re-bootstrapping.

## Cost ceiling

Steady-state running cost (us-east-1):

| Line | $/month |
| --- | ---: |
| NAT Gateway (single) | ~$32 |
| ALB (with app tier) | ~$22 |
| RDS `db.t4g.medium` single-AZ | ~$45 |
| ElastiCache `cache.t4g.small` | ~$25 |
| ECS Fargate (1 task) | ~$15 |
| Misc (S3, CloudWatch, ECR, Cognito) | <$5 |
| **Fixed total** | **~$144** |
| Bedrock token spend | variable |

`destroy.sh` brings this to **$0/mo** within ~15 minutes (RDS final-snapshot
takes the longest), assuming `DESTROY_BOOTSTRAP=yes` is also passed —
otherwise the retained state-backend KMS key + DynamoDB table cost ~$1.20/mo.

## Why this script exists

The agent that authored this deploy bundle is running in a sandbox
that cannot make outbound AWS API calls. The scripts here are the
hand-off — everything is parameterised, every confirm is logged,
every destructive op has a dry-run + rollback path.

Run them from a workstation that has:

- AWS credentials (via `AWS_PROFILE` or env vars) for the target account.
- The standard CLI deps: `aws`, `terraform >= 1.10`, `jq`, `bash >= 4`.

Everything else flows from there.
