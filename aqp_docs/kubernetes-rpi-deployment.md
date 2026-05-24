# rpi Kubernetes Deployment

AQP deploys to the `rpi_kubernetes` cluster through the sanctioned
Terraform runtime path. The source-of-truth HCL lives in
`aqp_platform/terraform/environments/rpi`, and the stack spec is
`aqp_platform/configs/terraform/rpi.yaml`.

## Prerequisites

- A kubeconfig that can reach the rpi cluster.
- A registry reachable by every rpi node.
- Immutable AQP image tag published with:

```bash
aqp-cli deploy publish-rpi --registry docker.io/<org> --tag <immutable-tag>
```

## Configure

Edit or override `aqp_platform/terraform/environments/rpi/terraform.tfvars`:

```hcl
rpi_kubeconfig_path = "~/.kube/config"
rpi_kube_context    = "rpi"
rpi_namespace       = "aqp"
rpi_image_registry  = "docker.io/<org>"
app_version         = "<immutable-tag>"
rpi_ingress_host    = "aqp.example.com"
auth0_domain        = "example.us.auth0.com"
auth0_audience      = "https://aqp/api"
auth0_client_id     = "<spa-client-id>"
```

## Deploy

Use the AQP control plane or Terraform directly:

```bash
terraform -chdir=aqp_platform/terraform/environments/rpi init
terraform -chdir=aqp_platform/terraform/environments/rpi plan
terraform -chdir=aqp_platform/terraform/environments/rpi apply
```

The backend control-plane routes dispatch the same stack through
`aqp.tasks.terraform_tasks.run_rpi_stack`, preserving `terraform_runs`
ledger rows and progress streams.

## Cold-start order

For first-time bootstrap on a new machine, run in this order so each
dependency exists before the next one:

1. Build and push immutable AQP images (`aqp-cli deploy publish-rpi ...`).
2. Set image tags and Auth0 values in `aqp_platform/terraform/environments/rpi/terraform.tfvars`.
3. Run Terraform from CLI (`init`, `plan`, `apply`) until the core stack
   is healthy.
4. Start/verify API + Celery + Redis + Postgres.
5. Use `/control-plane/kubernetes/targets/rpi/*` for ongoing operations.

Why this order matters:

- Terraform subprocess execution itself only needs Terraform + kubeconfig.
- Control-plane-triggered runs additionally need Celery broker/worker.
- Run history and richer status views depend on Postgres/Redis availability.

## Provider download resilience (flaky network / IPv6 issues)

When `terraform init` intermittently fails to download providers, use a
Terraform CLI config file with `provider_installation` mirrors and point
the runtime at it with `AQP_TERRAFORM_CLI_CONFIG_FILE`.

Example `terraform.tfrc`:

```hcl
provider_installation {
  filesystem_mirror {
    path    = "C:/terraform/provider-mirror"
    include = ["hashicorp/*", "kreuzwerker/*", "auth0/*"]
  }
  direct {
    exclude = ["hashicorp/*", "kreuzwerker/*", "auth0/*"]
  }
}
```

Then set:

```bash
export AQP_TERRAFORM_CLI_CONFIG_FILE=/absolute/path/to/terraform.tfrc
```

The runtime also retries transient `terraform init` network/provider
failures with bounded exponential backoff. Tune with:

- `AQP_TERRAFORM_INIT_RETRY_ATTEMPTS`
- `AQP_TERRAFORM_INIT_RETRY_BACKOFF_SECONDS`
- `AQP_TERRAFORM_INIT_RETRY_MAX_BACKOFF_SECONDS`

## Rollback

Re-apply the previous immutable image tag or run:

```bash
terraform -chdir=aqp_platform/terraform/environments/rpi destroy
```

Long-running Terraform jobs remain halt-able through `/terraform/halt`
and the global frontend kill switch.
