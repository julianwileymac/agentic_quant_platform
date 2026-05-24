# IaC runbook

"I want to provision X" recipes for the Terraform IaC control plane.

## Quick reference

| Task                                       | Recipe                                                  |
| ------------------------------------------ | ------------------------------------------------------- |
| Stand up local AQP on a laptop             | [Local environment](#local-environment)                 |
| Stand up AQP on rpi_kubernetes             | [rpi Kubernetes environment](#rpi-kubernetes-environment) |
| Stand up paper-trading on GCP              | [Paper environment](#paper-environment)                 |
| Stand up production on AWS                 | [Live environment](#live-environment)                   |
| Stand up the seeded Wiley Tech home on Azure | [Wiley Tech environment](#wiley-tech-environment)     |
| Add a new module kind to the codegen       | [Add a module kind](#add-a-module-kind)                 |
| Add a Terraform stack via the API          | [Create a stack via API](#create-a-stack-via-api)       |
| Plan / apply / destroy from the UI         | [Lifecycle from the frontend](#lifecycle-from-the-frontend) |
| Configure HCP Terraform as state backend   | [HCP Terraform](#hcp-terraform)                         |
| Wire OPA policy enforcement                | [Policy enforcement](#policy-enforcement)               |

## Local environment

```bash
cd aqp_platform/terraform/environments/local
terraform init
terraform plan
terraform apply
```

What this provisions:

- Postgres / MinIO / Redis containers via `kreuzwerker/docker`.
- Minikube / kind cluster + namespaces (`aqp-local` / `aqp-paper` /
  `aqp-live` / `aqp-backtest` / `aqp-system` / `aqp-terraform`).
- Helm baseline: cert-manager / ESO / KEDA / ingress-nginx /
  kube-prometheus / otel-operator / istio.
- KEDA `ScaledObject` per Celery queue (including the new
  `terraform` queue).
- Per-bot Deployment with `aqp-data-mcp` sidecar (zero-egress
  NetworkPolicy on the agent container).
- Local Docker registry on `:5000`.

State is local (`aqp_platform/terraform/environments/local/terraform.tfstate`).

## rpi Kubernetes environment

```bash
aqp deploy publish-rpi --registry ghcr.io/<org> --tag <immutable-tag>
terraform -chdir=aqp_platform/terraform/environments/rpi init
terraform -chdir=aqp_platform/terraform/environments/rpi plan
terraform -chdir=aqp_platform/terraform/environments/rpi apply
```

Recommended bootstrap sequence for first-time bring-up:

1. CLI-first Terraform apply until base services are healthy.
2. Verify API + Celery + Redis + Postgres are reachable.
3. Move to control-plane actions (`/control-plane/kubernetes/targets/rpi/*`).

This avoids enqueue/stream confusion during cold start when broker/DB
are still bootstrapping.

### Provider mirror + init retries

When provider downloads are unstable, define a Terraform CLI config file
with `provider_installation` mirror rules and point AQP at it:

```bash
export AQP_TERRAFORM_CLI_CONFIG_FILE=/absolute/path/to/terraform.tfrc
export AQP_TERRAFORM_INIT_RETRY_ATTEMPTS=5
export AQP_TERRAFORM_INIT_RETRY_BACKOFF_SECONDS=2
export AQP_TERRAFORM_INIT_RETRY_MAX_BACKOFF_SECONDS=30
```

`TerraformExecutor` applies bounded retries for transient `terraform init`
failures and reuses `AQP_TERRAFORM_PLUGIN_CACHE_DIR` between runs.

## Paper environment

```bash
cd aqp_platform/terraform/environments/paper
export TF_VAR_gcp_project_id=<your-gcp-project>
export TF_VAR_primary_domain=paper.aqp.example
terraform init -backend-config="bucket=aqp-terraform-state-paper"
terraform plan
terraform apply
```

What this provisions:

- GKE cluster (auto-promoted from `AQP_DEFAULT_CLOUD_PROVIDER=gcp`).
- Cloud SQL Postgres (single AZ — cost-optimised for paper).
- GCS bucket + Memorystore Redis.
- GCP Secret Manager `ClusterSecretStore` (ESO).
- Bot Deployments with `dry_run=true` for paper trading.
- 100% traffic to the Vite frontend (no canary split in paper).

## Live environment

```bash
cd aqp_platform/terraform/environments/live
export TF_VAR_aws_subnet_ids='["subnet-aaaa", "subnet-bbbb", "subnet-cccc"]'
export TF_VAR_primary_domain=app.wiley.tech
terraform init  # picks up backend.tf with S3 + DynamoDB locking
terraform plan
terraform apply
```

What this provisions:

- EKS cluster Multi-AZ.
- RDS Multi-AZ Postgres + S3 versioning + ElastiCache 7+ cluster
  mode.
- AWS Secrets Manager `ClusterSecretStore`.
- Bot Deployments live (`dry_run=false`); `live_control=true` on
  the actor's `Membership` is required to trigger orders.
- Full prod sizing for KEDA `maxReplicaCount` (50 default / 100
  ML / 200 backtest / 30 agents / 10 terraform).

## Wiley Tech environment

This is the seeded production home for the org provisioned by
Alembic 0051. Pinned to the Wiley Tech Entra tenant.

```bash
cd aqp_platform/terraform/environments/wiley-tech
export TF_VAR_azure_tenant_id=<wiley tenant id>
export TF_VAR_azure_subscription_id=<sub id>
export TF_VAR_azure_resource_group=aqp-wiley-tech
export TF_VAR_azure_keyvault_url=https://aqp-wiley-tech-kv.vault.azure.net/
terraform init  # picks up backend.tf with Azure Blob state
terraform plan
terraform apply
```

What this provisions:

- AKS cluster + Azure Workload Identity for ESO.
- Azure PostgreSQL Flexible Server (Zone-Redundant HA).
- ADLS Gen2 storage account (HNS enabled).
- Azure Cache for Redis (Standard, TLS-only).
- Azure Key Vault `ClusterSecretStore` synced via ESO Workload
  Identity.
- ACR registry for AQP images.

## Add a module kind

1. Add the kind to `TERRAFORM_MODULE_KINDS` in
   [`aqp/persistence/models_terraform.py`](../aqp/persistence/models_terraform.py).
2. Create the Jinja2 template at
   `aqp/terraform/codegen/templates/<kind>_<cloud>.tf.j2` (and a
   `_local` fallback).
3. (Optional) Mirror as a native HCL module under
   `aqp_platform/terraform/modules/<kind>/`.
4. Operators create a stack via `POST /terraform/stacks` with
   `module_kind: "<kind>"`.

## Create a stack via API

```bash
curl -X POST http://localhost:8000/terraform/stacks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "Bronze tier storage",
    "slug": "bronze-storage",
    "module_kind": "storage",
    "cloud_provider": "aws",
    "environment": "live",
    "variables": {
      "aws_region": "us-east-1",
      "aws_subnet_ids": ["subnet-aaa", "subnet-bbb", "subnet-ccc"],
      "bucket_name": "aqp-bronze",
      "db_storage_gb": 500
    },
    "backend": { "kind": "s3", "config": { "bucket": "aqp-tf-state", "key": "bronze-storage.tfstate" } },
    "tags": { "tier": "bronze" }
  }'
```

Response includes `spec_version_id` (immutable, hash-locked).

Then create a workspace + plan:

```bash
# Workspace
curl -X POST http://localhost:8000/terraform/workspaces \
  -H "Content-Type: application/json" -H "Authorization: Bearer <token>" \
  -d '{ "slug": "bronze-live", "name": "Bronze (live)", "stack_spec_id": "<id>", "environment": "live", "state_backend": "s3" }'

# Plan
curl -X POST http://localhost:8000/terraform/workspaces/<workspace_id>/plan \
  -H "Authorization: Bearer <token>"
```

Subscribe to live progress at `wss://<host>/terraform/ws/runs/<run_id>`.

## Lifecycle from the frontend

Navigate to `/infra/terraform`, click a workspace row → land on
`/infra/terraform/workspaces/[id]`:

1. Click **Plan** → enqueues plan task; result lands in
   `awaiting_approval`.
2. Review the plan summary on the run detail page (live WS stream).
3. Click **Apply this plan** on the plan run row.
4. Apply executes → state version snapshotted → outputs visible in
   the "Latest state outputs" card.
5. **Destroy** is friction-gated: type the workspace slug to confirm.

## HCP Terraform

1. Create an HCP Terraform organization + workspaces in the HCP UI.
2. Set `AQP_HCP_TOKEN` (preferred: via `CredentialResolver`),
   `AQP_HCP_ORGANIZATION`, `AQP_TERRAFORM_STATE_BACKEND=hcp`.
3. Set the stack spec's `backend.kind="hcp"` and the workspace's
   `hcp_workspace_id`.
4. The runtime now drives runs through
   [`HcpClient`](../aqp/terraform/hcp_client.py) instead of the local
   subprocess (no `terraform` binary required on the runner pod).

## Policy enforcement

1. Author OPA Rego policies that target Terraform plan JSON
   (the runtime emits `tfplan.binary.json` via `terraform show -json`).
2. Insert a `TerraformPolicyAttachment` row binding the policy file
   URI to a workspace.
3. Set `hard_mandatory=True` to block apply on violation;
   `hard_mandatory=False` emits a warning.
4. When `opa` is on PATH the runtime invokes
   `opa eval -i tfplan.json -d policy.rego "data.aqp.terraform.deny"`.
   Without OPA installed the check no-ops cleanly.
