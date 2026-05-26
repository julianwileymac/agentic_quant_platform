# `infrastructure/` — Multi-account AWS Terraform monorepo

Multi-account AWS landing zone + per-environment EKS + supporting
managed services. Coexists with the existing
[`aqp_platform/terraform/`](../aqp_platform/terraform/) tree, which
keeps Cloudflare Zero Trust + Auth0 + on-prem rpi/tower/live.

## Layout

```
infrastructure/
├── bootstrap/                  one-time seed (S3 backend + KMS + DynamoDB + OIDC)
├── envs/
│   ├── shared-services/        one composition: ECR, CodeArtifact, ArgoCD hub
│   ├── dev/                    workload account composition
│   ├── staging/
│   └── prod/
├── modules/                    reusable building blocks (see §Modules)
├── policies/{rego,sentinel}/   compliance gates
├── gitops/                     ArgoCD app-of-apps + ApplicationSets
└── tests/{terratest,terraform-test}/
```

## Modules

| Module | Purpose |
| --- | --- |
| `landing-zone` | AWS Organizations + Control Tower enrollment + 5 OUs |
| `account` | Service-Catalog-driven account factory wrapper |
| `vpc` | /16 VPC with private + public + intra subnets + VPC endpoints |
| `eks-cluster` | EKS 1.32 control plane + IRSA + addons |
| `eks-node-groups` | general (m6i) + compute (c6i) + gpu (g5) + spot |
| `karpenter-bootstrap` | Karpenter v1 IRSA + NodePool + EC2NodeClass |
| `ecr-repositories` | Per-service ECR with scan-on-push + cross-region replication |
| `rds-postgres` | Multi-AZ Postgres + KMS + IAM auth |
| `s3-data-lake` | Parquet bucket + Object Lock variant for audit |
| `msk-kafka` | Managed Kafka |
| `airflow` | Self-managed Airflow on EKS (NOT MWAA — needs LineageWriter) |
| `eso-bootstrap` | External Secrets Operator IRSA + Helm |
| `argocd-bootstrap` | ArgoCD HA + app-of-apps seed |
| `observability-stack` | kube-prometheus-stack + Thanos + Loki + Tempo + Grafana + ADOT |
| `iam-irsa-roles` | Per-SA IAM role module |
| `route53-zones` | Public + private zones |
| `acm-certificates` | Let's Encrypt + ACM Private CA |
| `acm-pca` | Private CA for internal mTLS |
| `github-oidc` | GitHub Actions OIDC trust per account |
| `codepipeline` / `codebuild` / `codeartifact` | AWS-native CI/CD parity |

## State backend

Per `bootstrap/`:

- Bucket: `aqp-tfstate-${account_alias}` (one per workload account
  + one for `shared-services`).
- Key convention: `${env}/${stack}.tfstate` (e.g.
  `s3://aqp-tfstate-shared/shared-services/argocd.tfstate`).
- Versioning + encryption (SSE-KMS) + Object Lock (Compliance, 30
  days) so accidental deletes are recoverable.
- Locking via the AWS provider's native S3 locking
  (`use_lockfile = true`); a DynamoDB table is provisioned but
  unused, kept as a 1-line rollback.

## Cross-account assume-role

Every workload-environment composition assumes
`arn:aws:iam::${account_id}:role/AqpTerraformExecutionRole` from the
`shared-services` plane via `sts:AssumeRole` with `external_id`. The
trust policy is provisioned by the `landing-zone` module.

## Hash-locked spec versions

Per AGENTS rules 42 + 43, every `terraform apply` flows through the
control-plane `TerraformRuntime` and persists an immutable
`terraform_stack_spec_versions` row. The `aqp_admin` Terraform
runner UI surfaces the spec hash + run id alongside the diff.

## Validation

```bash
# Format + validate every module + composition
find . -type d -name modules -prune -o -type d -name '.terraform' -prune \
  -o -type f -name '*.tf' -print | xargs -I{} dirname {} | sort -u \
  | xargs -I{} sh -c 'cd {} && terraform fmt -check && terraform init -backend=false && terraform validate'

# Static security review
tfsec .

# Module unit tests
cd tests/terratest && go test -v ./...
```

## Apply order (cold start)

1. `bootstrap/` (hand-applied with local state)
2. `envs/shared-services/` (ECR, CodeArtifact, ArgoCD hub)
3. `envs/dev/` (full stack)
4. `envs/staging/` (after dev burns in)
5. `envs/prod/` (after staging burns in; 4-eyes approval)
