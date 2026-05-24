# MLOps Pipelines (Argo + Dagster)

This package provides reusable pipeline recipes for:

1. Raw ingestion to MinIO (HTTP/REST/S3/filesystem)
2. Dagster asset materialization from MinIO to PostgreSQL
3. Hybrid Dagster -> Argo heavy transforms
4. Vector sync to Milvus and ChromaDB
5. Incremental CDC from PostgreSQL source tables

## Apply Kubernetes resources

```bash
kubectl apply -k kubernetes/mlops/pipelines/
```

## Submit pipeline workflows manually

```bash
# Raw ingest
argo submit --from workflowtemplate/pipeline-raw-ingest -n mlops \
  -p source_type=http \
  -p source_name=sample-http \
  -p source_uri=https://example.com/data.json

# Heavy transform
argo submit --from workflowtemplate/pipeline-heavy-transform -n mlops \
  -p source_key=raw/sample-http/latest.json

# Vector sync
argo submit --from workflowtemplate/pipeline-vector-sync -n mlops \
  -p source_key=processed/heavy/sample.json

# CDC incremental sync
argo submit --from workflowtemplate/pipeline-cdc-sync -n mlops \
  -p pipeline_name=cdc-source-events \
  -p source_table=source_events
```

## Scheduling

Two cron workflows are included:

- `pipeline-raw-ingest-hourly`
- `pipeline-cdc-sync-hourly`

Suspend/resume as needed:

```bash
kubectl patch cronworkflow pipeline-raw-ingest-hourly -n mlops --type merge -p '{"spec":{"suspend":true}}'
kubectl patch cronworkflow pipeline-cdc-sync-hourly -n mlops --type merge -p '{"spec":{"suspend":true}}'
```

## Production hardening TODOs

- Replace placeholder image tag with a pinned image digest.
- Move credentials to ExternalSecrets or sealed secrets.
- Add source-specific pagination/state for REST ingestion.
- Add dead-letter handling and retention lifecycle policies.
- Add SLO alerts on workflow failures and lag.

