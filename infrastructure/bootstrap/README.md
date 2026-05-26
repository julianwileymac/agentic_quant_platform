# bootstrap/

One-time seed. Apply with **local state** before any other
composition.

```bash
export AWS_PROFILE=aqp-shared-platform-admin
cd infrastructure/bootstrap

terraform init      # local state — no backend block
terraform apply -var=account_alias=shared

# Repeat per workload account, swapping the AWS_PROFILE + alias:
terraform apply -var=account_alias=dev
terraform apply -var=account_alias=staging
terraform apply -var=account_alias=prod
```

Outputs are referenced by every other composition via `data`
blocks (no `terraform_remote_state` cross-coupling).

## Subsequent re-applies

The only legitimate reason to re-apply this stack is to rotate the
GitHub Actions OIDC thumbprints (when GitHub rotates their CA).
Everything else is immutable.

## Tear-down

Don't. The KMS key, S3 bucket, and OIDC provider underpin every
other stack; tearing them down requires a documented compliance
event + manual coordination with the security officer (owner of
the audit-archive Object Lock).
