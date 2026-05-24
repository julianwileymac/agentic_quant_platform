# Terraform IaC Discovery — AQP service inventory

This document is the pre-work output the plan asked for (Phase E
prerequisite from the prompt's STEP 5). It maps every AQP service /
stateful resource / external integration to the terraform module
that provisions it.

Last regenerated for Alembic head `0051_seed_wiley_tech`. Re-run
`docker exec aqp-api python -m scripts.iceberg_smoke --inspect-only`
to confirm the Iceberg + Postgres assumptions below still hold.

## 1. Services to be containerized

Each service is provisioned by exactly one terraform module. The
column "Module" maps to `aqp_platform/terraform/modules/<name>`.

| Service / Pod | Image | Port | Module | Notes |
| --- | --- | --- | --- | --- |
| `aqp-api` (FastAPI) | `aqp-api:latest` | 8000 | `pipeline` | Main app server |
| `aqp-worker` (Celery) | `aqp-worker:latest` | – | `faas` | Per-queue replica set |
| `aqp-agent` + `aqp-data-mcp` sidecars | `aqp-agent:latest` + `aqp-data-mcp:latest` | – | `agents` | Two-container pod; zero egress |
| `aqp-frontend` (Vite/Next) | `aqp-frontend:latest` | 3001 | `pipeline` | SPA |
| Postgres | `postgres:16-alpine` | 5432 | `storage` + `database` | PgBouncer in front |
| Redis Stack | `redis/redis-stack:7.4.0-v0` | 6379 | `storage` | DB 0 = broker, 1 = kill-switch, 2 = RediSearch |
| MinIO | `minio/minio:latest` | 9000/9001 | `storage` | S3-compat |
| Polaris (Iceberg) | `apache/polaris:latest` | 8181 | `storage` | Iceberg catalog REST |
| DataHub (`gms` + `frontend`) | `linkedin/datahub-gms` etc. | 8080/9002 | `pipeline` | Metadata |
| Airbyte | `airbyte/server:latest` | 8001 | `pipeline` | Connector builder |
| Dagster | `dagster:latest` | 3001 | `pipeline` | Asset orchestrator |
| MLflow | `python:3.11` + `mlflow serve` | 5000 | `pipeline` | Experiment tracking |
| KEDA operator | `kedacore/keda:latest` | – | `faas` | Helm release |
| External Secrets Operator | `external-secrets/external-secrets:latest` | – | `secrets` | Helm release |
| cert-manager | `quay.io/jetstack/cert-manager-controller:latest` | – | `kubernetes` | Helm release |
| NGINX Ingress | `registry.k8s.io/ingress-nginx/controller` | 80/443 | `networking` | Helm release |
| kube-prometheus-stack | bundle | – | `kubernetes` | Helm release |
| OTel Operator | `otel/opentelemetry-operator` | – | `kubernetes` | Helm release |
| Istio (base + istiod) | `docker.io/istio/*` | – | `kubernetes` | mTLS |
| `aqp-terraform-runner` | `aqp-terraform-runner:latest` | – | `kubernetes` (own ns) | Plan/apply executor |

## 2. Stateful resources (per cloud)

Provisioned by the `storage` module. Cloud-conditional `for_each`
selects the right resource set.

| Resource | Local | AWS | GCP | Azure | rpi_cluster |
| --- | --- | --- | --- | --- | --- |
| Relational DB | Postgres container | RDS PG Multi-AZ | Cloud SQL PG | Azure DB PG Flex | StatefulSet via Helm |
| Object store | MinIO container | S3 bucket + LC rules | GCS bucket | ADLS Gen2 | MinIO StatefulSet |
| Cache / broker | Redis Stack container | ElastiCache (Redis 7+) | Memorystore | Azure Cache for Redis | Redis StatefulSet |
| Vector store | Redis Stack (RediSearch) | same ElastiCache | same Memorystore | same Azure Cache | same Redis (RediSearch) |
| Iceberg catalog | Local FS catalog | AWS Glue Data Catalog | Dataplex (GCS-backed) | Azure Purview | Polaris on-cluster |

## 3. External integrations + credentials

Every `AQP_*` env var that holds a secret resolves through
`aqp.credentials.CredentialResolver`. The `secrets` module
materialises one `ExternalSecret` per `(service, purpose)` pair so the
broker API keys, DB password, MinIO root creds, etc. all sync from
the matching cloud's secret manager (or HashiCorp Vault).

| Integration | Credential service key | Backed by |
| --- | --- | --- |
| Alpaca | `alpaca:default` | `AQP_ALPACA_API_KEY` + secret |
| Tradier | `tradier:default` | `AQP_TRADIER_TOKEN` |
| IBKR | `ibkr:default` | `AQP_IBKR_*` |
| Polaris (Iceberg) | `polaris:oauth` + `polaris:rest` | `AQP_POLARIS_CLIENT_*` |
| MinIO | `minio:static` | `AQP_S3_*` |
| Trino | `trino:basic` | `AQP_TRINO_*` |
| Neo4j | `neo4j:basic` | `AQP_NEO4J_*` |
| Alpha Vantage | `alpha_vantage:default` | `AQP_ALPHA_VANTAGE_API_KEY` |
| FRED | `fred:default` | `AQP_FRED_API_KEY` |
| MathPix | `mathpix:default` | `AQP_MATHPIX_APP_KEY` |
| MSAL / Entra | `msal:client_secret` | `AQP_MSAL_CLIENT_SECRET` |
| HCP Terraform | `hcp:token` | `AQP_HCP_TOKEN` |
| Airbyte | `airbyte:default` | `AQP_AIRBYTE_AUTH_TOKEN` |
| DataHub | `datahub:default` | `AQP_DATAHUB_TOKEN` |
| GCP BigQuery | (workload identity) | service account |
| AWS APIs | (IRSA) | role |
| Azure APIs | (Workload Identity) | managed identity |

## 4. Celery queues + KEDA ScaledObjects

The `faas` module provisions a `ScaledObject` per queue. List taken
from `aqp/tasks/celery_app.py::task_routes`:

| Queue | Source modules | Min replicas | Max replicas |
| --- | --- | --- | --- |
| `default` | `chat_tasks`, `llm_tasks`, `finops_tasks`, `analytics_tasks`, `cache_tasks`, `ownership_tasks`, `agent_watchdog_tasks` | 1 | 20 |
| `backtest` | `backtest_tasks`, `optimize_tasks`, `optimization_tasks`, `bot_tasks.run_bot_backtest` | 0 | 100 |
| `agents` | `agent_tasks`, `agentic_backtest_tasks`, `research_tasks`, `selection_tasks`, `analysis_tasks`, `entity_tasks`, `equity_report_tasks`, `bot_tasks.chat_research_bot`, `analysis_flow_tasks`, `orchestration_tasks` | 0 | 20 |
| `ml` | `ml_tasks`, `ml_test_tasks`, `feature_set_tasks` | 0 | 50 |
| `ingestion` | `ingestion_tasks`, `regulatory_tasks`, `engine_tasks`, `airbyte_tasks`, `datahub_tasks`, `streaming_link_tasks`, `dataset_preset_tasks`, `dataset_upload_tasks`, `data_metadata_tasks`, `visualization_tasks` | 0 | 30 |
| `paper` | `paper_tasks`, `bot_tasks.run_bot_paper`, `rl_tasks.paper_trade_rl` | 0 | 10 |
| `training` | `training_tasks`, `finetune_tasks`, `rl_tasks` (train/eval/replay/walk-forward/bestof) | 0 | 20 |
| `rag` | `rag_tasks` | 0 | 10 |
| `factors` | `factor_tasks` | 0 | 20 |
| `hft` | `hft_tasks` | 0 | 5 |
| `terraform` | `terraform_tasks` (5 ops) | 0 | 10 |

## 5. Existing docker-compose services to be deprecated

Once the equivalent terraform module ships, the matching
`docker-compose*.yml` profile becomes legacy:

- `aqp_platform/compose/docker-compose.yml` base profile → `storage` + `pipeline` + `database` modules.
- `aqp_platform/compose/docker-compose.viz.yml` → `pipeline` (Superset / Trino / Polaris / Airbyte / Dagster).
- `aqp_platform/compose/docker-compose.platform.yml` → `kubernetes` + `pipeline` (DataHub / Loki / VictoriaMetrics).

Each environment composition under `aqp_platform/terraform/environments/` selects
the corresponding subset (local picks docker; cloud envs pick the
cloud-native equivalents).

## 6. Module dependency graph

```
networking ─┐
            ├─→ kubernetes ─┬─→ secrets ─┬─→ storage ─→ database ─→ pipeline
            │               │            └─→ registry             │
            │               └─→ faas ─→ agents ─────────────────┘
            └─→ networking output also feeds storage (bucket DNS)
```

Each environment composition under `aqp_platform/terraform/environments/*`
instantiates the modules in this order. Outputs from earlier
modules (state backend URI, kubeconfig, vault address, registry
URL, namespace map) are passed as inputs to later modules — never
hardcoded.

## 7. Tagging convention

Every resource consumes `local.common_tags`:

```
locals {
  common_tags = {
    environment      = var.environment   # local | paper | live | wiley-tech | sandbox
    "managed-by"     = "terraform"
    component        = "<module name>"
    version          = var.app_version
    organization     = var.organization_slug  # wiley-tech, default, ...
    workspace        = var.workspace_slug
  }
}
```

The `aqp.config.Settings.finops_labels()` helper emits the same shape
for the Celery/MLflow/progress emit path so cluster cost-attribution
tooling can join across both surfaces.
