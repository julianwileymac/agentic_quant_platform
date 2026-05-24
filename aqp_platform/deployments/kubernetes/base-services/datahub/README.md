# DataHub - Data Catalog

DataHub is an open-source metadata platform for data discovery, governance, and lineage tracking. This deployment includes the built-in Iceberg Catalog backed by MinIO.

## Prerequisites

- Existing PostgreSQL in `data-services` namespace with `datahub` database
- Existing MinIO in `data-services` namespace
- All DataHub components require amd64 (Java-based); scheduled on the control plane node

## Installation

### 1. Apply Kustomize Resources (secrets, ingress)

```bash
kubectl apply -k kubernetes/base-services/datahub/
```

### 2. Create MinIO Bucket for Iceberg

```bash
kubectl exec -n data-services deploy/minio -- \
  sh -c 'mc alias set local http://localhost:9000 minioadmin minioadmin123 && \
         mc mb local/iceberg-warehouse --ignore-existing'
```

### 3. Add Helm Repository

```bash
helm repo add datahub https://helm.datahubproject.io/
helm repo update
```

### 4. Install Prerequisites (Kafka, Elasticsearch)

```bash
helm install prerequisites datahub/datahub-prerequisites \
  --namespace data-services \
  -f values-prerequisites.yaml
```

Wait for all prerequisite pods to become ready:

```bash
kubectl get pods -n data-services -l app.kubernetes.io/instance=prerequisites --watch
```

### 5. Install DataHub

```bash
helm install datahub datahub/datahub \
  --namespace data-services \
  -f values-datahub.yaml
```

Wait for DataHub pods and the system-update job to complete:

```bash
kubectl get pods -n data-services -l app.kubernetes.io/instance=datahub --watch
```

## Access

| Endpoint | URL |
|----------|-----|
| DataHub UI | `http://datahub.local` |
| GMS API | `http://datahub.local:8080` (internal: `datahub-datahub-gms.data-services:8080`) |
| Iceberg REST Catalog | `http://datahub-datahub-gms.data-services:8080/iceberg` |

Default credentials: `datahub` / `datahub`

## Architecture

```
                   ┌──────────────┐
                   │   Frontend   │ :9002
                   └──────┬───────┘
                          │
                   ┌──────▼───────┐
                   │     GMS      │ :8080  ─── Iceberg REST Catalog
                   └──┬───┬───┬───┘
                      │   │   │
         ┌────────────┘   │   └────────────┐
         ▼                ▼                ▼
  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
  │ PostgreSQL   │ │Elasticsearch│ │    Kafka      │
  │ (existing)   │ │  (new)      │ │   (new)       │
  └──────────────┘ └─────────────┘ └───┬──────┬────┘
                                       │      │
                                ┌──────▼──┐ ┌─▼────────┐
                                │MAE Cons.│ │MCE Cons.  │
                                └─────────┘ └───────────┘
```

## DataHub dbt Ingestion

To ingest dbt metadata into DataHub, create a recipe file:

```yaml
source:
  type: dbt
  config:
    manifest_path: /path/to/target/manifest.json
    catalog_path: /path/to/target/catalog.json
    target_platform: postgres
    include_column_lineage: true

sink:
  type: datahub-rest
  config:
    server: "http://datahub-datahub-gms.data-services:8080"
```

Run ingestion:

```bash
datahub ingest -c dbt-recipe.yaml
```

## Native Ingestion CronJobs

The repository includes native DataHub ingestion recipes and scheduled CronJobs:

- `datahub-ingest-postgres`
- `datahub-ingest-minio-s3`
- `datahub-ingest-mlflow`
- `datahub-ingest-iceberg`
- `datahub-ingest-aqp-iceberg`
- `datahub-ingest-aqp-mlflow`
- `datahub-ingest-kafka`
- `datahub-ingest-grafana`
- `datahub-ingest-aqp-openapi`

All CronJobs are created in **suspended** mode by default for safe rollout.

Resources are managed under:

- `configmap-ingestion-settings.yaml` (non-secret coordinates)
- `configmap-ingestion-recipes.yaml` (recipe templates)
- `secret-ingestion-secrets.yaml` (dedicated ingestion credentials/token)
- `cronjob-ingest-*.yaml` (schedules)

Naming conventions used for operations:

- CronJobs: `datahub-ingest-<source>` and `datahub-metadata-bridge`
- Labels: `app.kubernetes.io/component=metadata-ingestion`
- Recipe keys in ConfigMap: `recipe-<source>.yaml`

### Enable Ingestion Jobs

1. Set real credentials/token in `secret-ingestion-secrets.yaml`.
   - `DATAHUB_TOKEN` for DataHub writes
   - `INGEST_POSTGRES_PASSWORD` for PostgreSQL ingestion
   - `INGEST_MINIO_*` for S3/MinIO and Iceberg warehouse reads
   - `INGEST_GRAFANA_SERVICE_ACCOUNT_TOKEN` for Grafana dashboard ingestion
2. Apply DataHub kustomize resources:

```bash
kubectl apply -k kubernetes/base-services/datahub/
```

3. Unsuspend jobs:

```bash
kubectl patch cronjob -n data-services datahub-ingest-postgres --type merge -p '{"spec":{"suspend":false}}'
kubectl patch cronjob -n data-services datahub-ingest-minio-s3 --type merge -p '{"spec":{"suspend":false}}'
kubectl patch cronjob -n data-services datahub-ingest-mlflow --type merge -p '{"spec":{"suspend":false}}'
kubectl patch cronjob -n data-services datahub-ingest-iceberg --type merge -p '{"spec":{"suspend":false}}'
kubectl patch cronjob -n data-services datahub-ingest-kafka --type merge -p '{"spec":{"suspend":false}}'
kubectl patch cronjob -n data-services datahub-ingest-grafana --type merge -p '{"spec":{"suspend":false}}'
kubectl patch cronjob -n data-services datahub-ingest-aqp-openapi --type merge -p '{"spec":{"suspend":false}}'
```

4. Trigger a manual run (example):

```bash
kubectl create job -n data-services --from=cronjob/datahub-ingest-postgres datahub-ingest-postgres-manual
kubectl logs -n data-services job/datahub-ingest-postgres-manual
```

## Source Inventory

| Source | DataHub path | Notes |
| --- | --- | --- |
| rpi Kubernetes MinIO | `recipe-minio-s3.yaml` | Scans pipeline, model, MLflow, AQP, and Iceberg buckets/prefixes. |
| rpi Kubernetes Iceberg | `recipe-iceberg-rest.yaml` | DataHub GMS Iceberg REST catalog, platform instance `rpi-kubernetes`. |
| AQP Iceberg lake | `recipe-aqp-iceberg-rest.yaml` | Same REST catalog with AQP warehouse/platform instance naming. |
| rpi/AQP MLflow | `recipe-mlflow*.yaml` | Logical platform instances over the shared in-cluster MLflow tracking service. |
| rpi Kafka | `recipe-kafka.yaml` | Strimzi bootstrap plus Apicurio schema registry. |
| rpi Grafana | `recipe-grafana.yaml` | Requires a Grafana service account token. |
| AQP APIs | `recipe-aqp-openapi.yaml` | Ingests `http://api.aqp.svc.cluster.local:8000/openapi.json`. |

## Argo Orchestration

`kubernetes/mlops/pipelines/workflowtemplate-datahub-ingestion.yaml` can trigger
groups of the suspended DataHub CronJobs from Argo:

```bash
argo submit -n mlops --from workflowtemplate/datahub-ingestion \
  -p source_group=all \
  -p job_suffix=manual
```

Supported `source_group` values are `all`, `lakehouse`, `mlflow`, `platform`,
`api`, and `bridge`. The template uses the `argo-workflow` service account and
the `rbac-argo-datahub-ingestion.yaml` RoleBinding to create and wait on jobs in
the `data-services` namespace.

`cronworkflow-datahub-ingestion-daily.yaml` adds a suspended daily Argo schedule
for the full sync.

## Dagster Orchestration

Dagster user code in `pipelines/dagster_user_code/datahub_assets.py` exposes
assets for the same source groups and submits the Argo `datahub-ingestion`
WorkflowTemplate. The assets are registered in `definitions.py` as individual
jobs plus `datahub_full_sync_job` and `datahub_daily_schedule`.

## Metadata Bridge (Argo, Dagster, Prefect, Flink, Milvus, Chroma)

The hybrid metadata bridge job emits metadata directly to DataHub for sources that
are not fully covered by native connectors in this repository:

- Argo Workflows (`WorkflowTemplate` / `CronWorkflow` naming metadata)
- Dagster assets/jobs naming metadata
- Prefect flow naming metadata (runtime is managed separately)
- Flink job naming metadata
- Milvus collection metadata
- ChromaDB collection metadata

Managed resources:

- `configmap-metadata-bridge.yaml`
- `cronjob-metadata-bridge.yaml`

Enable it after ingestion credentials are set:

```bash
kubectl patch cronjob -n data-services datahub-metadata-bridge --type merge -p '{"spec":{"suspend":false}}'
kubectl create job -n data-services --from=cronjob/datahub-metadata-bridge datahub-metadata-bridge-manual
kubectl logs -n data-services job/datahub-metadata-bridge-manual
```

## Upgrade

```bash
helm upgrade prerequisites datahub/datahub-prerequisites \
  --namespace data-services \
  -f values-prerequisites.yaml

helm upgrade datahub datahub/datahub \
  --namespace data-services \
  -f values-datahub.yaml
```

## Uninstall

```bash
helm uninstall datahub --namespace data-services
helm uninstall prerequisites --namespace data-services
```
