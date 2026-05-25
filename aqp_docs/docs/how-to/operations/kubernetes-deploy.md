---
title: 'Operations runbook — Kubernetes deployment'
summary: '- `kubectl` 1.30+ with a current context pointing at the target cluster. - Cluster admin (youll create namespaces + RBAC). - A container registry the cluster can pull from (Docker Hub / ECR / ACR / G...'
owner: sre-team
last_reviewed: 2026-05-25
audience: both
---

# Operations runbook — Kubernetes deployment

End-to-end walkthrough for shipping AQP to any Kubernetes cluster (EKS,
AKS, GKE, vanilla k3s, or the Raspberry Pi k3s cluster owned by
`rpi_kubernetes`). AQP is fully self-contained: every shared service it
depends on (Postgres, Redis, Kafka, MinIO, MLflow, observability stack,
etc.) ships in `aqp_platform/deployments/kubernetes/`. There is no implicit
dependency on `rpi_kubernetes` or any other repository.

## Prerequisites

- `kubectl` 1.30+ with a current context pointing at the target cluster.
- Cluster admin (you'll create namespaces + RBAC).
- A container registry the cluster can pull from (Docker Hub / ECR / ACR / GCR).
- An ingress controller (`ingress-nginx` recommended) and `cert-manager`
  with a `letsencrypt-prod` `ClusterIssuer` for the AQP TLS hosts.
- Auth0 tenant configured per
  [aqp_docs/architecture/decisions/003-auth0-zero-trust.md](../../architecture/decisions/003-auth0-zero-trust.md)
  (default tenant `aqp-fund.us.auth0.com`).
- Cluster operators / CRDs installed via
  [aqp_platform/scripts/cluster_install/](../../scripts/cluster_install/) (Strimzi,
  Spark Operator, OpenTelemetry Operator, Phoenix, Redpanda, etc.) - run
  the relevant installer before applying the AQP base kustomization.

## Targeted runbooks

- Two-node tower+laptop bootstrap: [tower-cluster-deploy.md](tower-cluster-deploy.md)
- Blue/green domain cutover: [aqp-fund-blue-green-cutover.md](aqp-fund-blue-green-cutover.md)

## Step 1 — provision Auth0 (one-time)

```powershell
$env:AUTH0_DOMAIN = "your-tenant.us.auth0.com"
$env:AUTH0_M2M_CLIENT_ID = "..."
$env:AUTH0_M2M_CLIENT_SECRET = "..."
$env:AQP_SYNC_URL = "https://api.aqp.enterprise.com/_internal/auth0/sync"

python aqp_platform/build/scripts/provision_auth0.py --dry-run    # preview
python aqp_platform/build/scripts/provision_auth0.py              # apply
```

This idempotently creates the API resource server, the four roles, and the post-login Action.

## Step 2 — generate the K8s ConfigMap + Secret scaffold

```powershell
make generate-config ENV=k8s
```

Produces:
- `aqp_platform/deployments/kubernetes/base/configmaps/aqp-config.yaml` (commit this)
- `aqp_platform/deployments/kubernetes/base/secrets/aqp-secrets.yaml.template` (DO NOT commit values — CI/CD or external-secrets-operator patches real values)

## Step 3 — build + push images

```powershell
$env:IMAGE_TAG = "rc-$(git rev-parse --short HEAD)-$(Get-Date -Format yyyy-MM-dd)"
make build-client IMAGE_TAG=$env:IMAGE_TAG
make build-cp IMAGE_TAG=$env:IMAGE_TAG

# Optional (only if the Dockerfiles exist in aqp_platform/build/docker/*)
make build-worker IMAGE_TAG=$env:IMAGE_TAG
make build-ingestion IMAGE_TAG=$env:IMAGE_TAG

docker login
docker push docker.io/julianwiley/aqp-client:$env:IMAGE_TAG
docker push docker.io/julianwiley/aqp-control-plane:$env:IMAGE_TAG
docker push docker.io/julianwiley/aqp-worker:$env:IMAGE_TAG
docker push docker.io/julianwiley/aqp-ingestion:$env:IMAGE_TAG
```

If `make build-worker` or `make build-ingestion` reports a missing Dockerfile,
pin those image tags to known-good prebuilt registry tags in the target overlay
before applying.

## Step 3b — one-shot Alembic migration (cluster)

After `aqp-api` is pullable on the cluster, run:

```powershell
kubectl apply -f aqp_platform/deployments/kubernetes/base/jobs/alembic-upgrade.yaml
kubectl -n aqp wait --for=condition=complete job/aqp-alembic-upgrade --timeout=900s
kubectl -n aqp logs job/aqp-alembic-upgrade
```

The Job uses the same `aqp-config` / `aqp-secrets` env as `aqp-core` and targets
`postgresql.aqp-data-services.svc.cluster.local` (the AQP-owned Postgres in the
`aqp-data-services` namespace). Re-apply only when you need a fresh
`upgrade head` (delete the previous Job first: `kubectl -n aqp delete job aqp-alembic-upgrade`).

`alembic/env.py` widens `alembic_version.version_num` to `VARCHAR(128)` automatically
before migrations run (revision slugs longer than 32 characters otherwise fail at
`0039_extended_instrument_taxonomy`).

### Brownfield Postgres (pre-Alembic or partial schema)

If `alembic upgrade head` fails with `DuplicateTable` / `DuplicateColumn`, the database
was created outside Alembic tracking. From a workstation with the API image and a
port-forward to cluster Postgres:

```powershell
kubectl -n aqp-data-services port-forward svc/postgresql 15432:5432
$env:AQP_POSTGRES_DSN = "postgresql+psycopg2://aqp:aqp@host.docker.internal:15432/aqp"
# Optional: stamp to the highest revision whose objects already exist, then upgrade.
# $env:AQP_ALEMBIC_STAMP_REVISION = "0015_dbt_foundation"
bash scripts/cluster_alembic_upgrade.sh
```

Use `AQP_POSTGRES_DSN` (maps to `settings.postgres_dsn`) — not a raw `DATABASE_URL`
alias. Migration `0040_normalized_identifiers_backfill` can take several minutes on
large `instruments` tables.

### Postgres prerequisites (`aqp-data-services`)

Migration `0045_pgvector_foundation` requires the `vector` extension in the **`aqp`**
database. On existing clusters (init script applied before the `aqp` DB was added),
run once as the Postgres superuser:

```powershell
kubectl -n aqp-data-services exec deploy/postgresql -- \
  psql -U postgres -d aqp -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Fresh installs use the AQP-owned `aqp_platform/deployments/kubernetes/base-services/postgres-shared/`
manifests, whose init SQL creates the `aqp` role/database and enables
`vector` there.

## Step 4 — pin the image tag in the target overlay

Edit `aqp_platform/deployments/kubernetes/overlays/<env>/kustomization.yaml`:

```yaml
images:
  - name: docker.io/julianwiley/aqp-client
    newTag: rc-abcdef01-2026-05-19
  ...
```

### Docker Hub pull secret (private repos)

Deployments reference `dockerhub-pull-secret`. Create it in both workload
namespaces before rollout:

```powershell
$env:DOCKERHUB_USER = "<dockerhub-username>"
$env:DOCKERHUB_TOKEN = "<dockerhub-access-token>"  # hub.docker.com → Account Settings → Security

kubectl create secret docker-registry dockerhub-pull-secret `
  --docker-server=https://index.docker.io/v1/ `
  --docker-username=$env:DOCKERHUB_USER `
  --docker-password=$env:DOCKERHUB_TOKEN `
  -n aqp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry dockerhub-pull-secret `
  --docker-server=https://index.docker.io/v1/ `
  --docker-username=$env:DOCKERHUB_USER `
  --docker-password=$env:DOCKERHUB_TOKEN `
  -n aqp-admin --dry-run=client -o yaml | kubectl apply -f -
```

Public repositories can omit the secret by removing `imagePullSecrets` from
the deployment manifests.

## Step 5 — apply

```powershell
# Dry-run first
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/tower-dev --dry-run=server

# Apply
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/tower-dev

# Verify
kubectl -n aqp get pods,svc,hpa,pdb
kubectl -n aqp-admin get pods,svc
```

## Step 6 — populate the Secret

If you're not using external-secrets-operator, populate the placeholder Secret manually:

```powershell
kubectl -n aqp create secret generic aqp-secrets `
  --from-literal=AQP_DATABASE_PASSWORD="<value>" `
  --from-literal=AQP_AUTH_M2M_CLIENT_SECRET="<value>" `
  --from-literal=AQP_SESSION_COOKIE_SECRET="<value>" `
  --dry-run=client -o yaml | kubectl apply -f -
```

For external-secrets-operator users, point an `ExternalSecret` at your secret store (Vault / SSM / Key Vault / Secret Manager) and let the operator create the K8s `Secret`.

## Step 7 — DNS + TLS

The Ingresses expect:
- `aqp.fund` -> `aqp-client` Service in the `aqp` namespace
- `api.aqp.fund` -> `aqp-core` Service in the `aqp` namespace
- `manage.aqp.fund` -> `aqp-cp` Service in the `aqp-admin` namespace

Point DNS at the NGINX Ingress controller's LoadBalancer IP. cert-manager handles TLS via the `letsencrypt-prod` ClusterIssuer (configure separately).

## Step 8 — smoke test

```powershell
# Client should serve the SPA shell
curl -fsS https://aqp.fund/ | findstr "<!doctype html"

# Control plane health (unauthenticated)
curl -fsS https://manage.aqp.fund/manage/health

# OpenAPI spec
curl -fsS https://manage.aqp.fund/manage/openapi.json | python -m json.tool | findstr title

# Cluster verification helper
bash scripts/verify_tower_cluster.sh
```

## Rollback

```powershell
# Re-apply the previous overlay with the previous image tag.
git checkout HEAD~1 -- aqp_platform/deployments/kubernetes/overlays/dev/kustomization.yaml
make deploy-k8s ENV=dev
```

Or, for an immediate rollback that doesn't touch git:

```powershell
kubectl -n aqp rollout undo deployment/aqp-client
kubectl -n aqp rollout undo deployment/aqp-core
kubectl -n aqp rollout undo deployment/aqp-worker
kubectl -n aqp-admin rollout undo deployment/aqp-cp
```
