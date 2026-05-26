# Multi-account rollout runbook

The Phase 4 Control Tower + cross-account IAM + dev->staging
promotion + IdP cutover. The Terraform code is shipped under
`infrastructure/`; this runbook is what the operator follows to
apply it.

## 1. Bootstrap

```bash
# In the AWS Org master account, with the platform-admin role:
cd infrastructure/bootstrap
export AWS_PROFILE=aqp-org-master
terraform init
terraform apply -var=account_alias=master
```

Capture the outputs (KMS arn, GitHub OIDC arn, etc.).

## 2. Landing zone

```bash
cd infrastructure/modules/landing-zone
terraform init
terraform apply
```

This stands up the 5 OUs + SCPs. The first `apply` takes ~15
minutes because Control Tower has to enrol every region one at a
time.

## 3. Workload accounts

For each workload account (dev, staging, prod), create the
account via the `account` module from the master account, then
re-run `bootstrap/` against the new account.

```bash
cd infrastructure
terraform apply \
  -target=module.account.dev \
  -var='dev_email=aws-aqp-dev@aqp.fund' \
  -var='external_id=...'
```

## 4. Per-environment composition

For each env (`dev`, `staging`, `prod`):

```bash
cd infrastructure/envs/dev
cp terraform.tfvars.example terraform.tfvars
# Fill in real values per the example.
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

## 5. Cross-account IAM

Provision the four canonical roles per blueprint §4.2:

- `AqpAdminDeploymentRole` (cross-account assume from
  shared-services)
- `AqpAdminReadOnlyAuditRole`
- `AqpAdminBreakGlassRole` (Deny-everything by default; attach
  the Lambda from §9.3 of the blueprint to attach
  `AdministratorAccess` on approved break-glass)
- `GitHubActionsDeployRole` (federated via the OIDC provider
  from `bootstrap/`)

These are wired through the `iam-irsa-roles` + `github-oidc`
modules per env. Confirm with:

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::${DEV_ACCOUNT_ID}:role/AqpAdminDeploymentRole \
  --role-session-name dev-smoke \
  --external-id "$EXTERNAL_ID"
```

## 6. Promote dev to staging

Use the `aqp_admin/src/aqp_admin/services/account_promoter.py`
wizard via the `/admin/accounts` UI. The wizard:

1. Replicates ECR artifacts cross-region.
2. Templates the staging Helm overlay from dev (with
   `prod.deny.json` allowlist filtering).
3. Applies the staging Terraform workspace.

The same wizard handles staging -> prod once the staging burn-in
period (recommended: 14 days) completes.

## 7. IdP cutover

If you are migrating from the existing Auth0 tenant to AWS IAM
Identity Center:

1. Provision IAM Identity Center via Control Tower (one-click).
2. Create the AQP application in Identity Center; copy the
   issuer URL + audience.
3. Set `AQP_AUTH_PROVIDER=aws_iam_identity_center` +
   `AQP_AUTH_OIDC_ISSUER=...` +
   `AQP_AUTH_OIDC_AUDIENCE=...`.
4. The
   [`AwsIamIdentityCenterProvider`](../../../aqp/auth/providers/aws_iam_identity_center.py)
   subclass auto-registers via the `IdentityProviderMeta`
   metaclass per AGENTS rule 27. No manual `@register` decorator.
5. Group sync: create `IdpGroupMapping` rows with
   `connection_kind="aws_iam_identity_center"` for every Identity
   Center group that should map to an AQP role.
6. Test login with a single staff account before flipping the
   default for the org.

## 8. Production cutover

Production cutover follows the same dev->staging recipe via
`account_promoter.py`. Step-up MFA + 4-eyes approval are
enforced server-side; the operator runs the wizard from the
admin UI.

After cutover:

- ArgoCD ApplicationSet picks up the prod cluster via its
  `aqp.io/managed=true` label.
- ArgoCD Image Updater auto-bumps image tags from new ECR
  digests when the GHA pipeline produces them.
- The legacy ADR-002 single-container Solara deployment is
  decommissioned in the follow-up `aqp_admin-overhaul-cleanup` PR.
