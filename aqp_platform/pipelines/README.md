# Pipeline Runtime Package

This directory contains reusable pipeline runtime code used by:

- Argo `WorkflowTemplate` / `CronWorkflow` jobs
- Dagster user-code assets and jobs

## Build image

```bash
docker build -f pipelines/Dockerfile -t ghcr.io/julianwiley/rpi-k8s-pipelines:latest .
```

## Push image

```bash
docker push ghcr.io/julianwiley/rpi-k8s-pipelines:latest
```

## Run task locally

```bash
python -m pipelines.cli raw-ingest \
  --source-type http \
  --source-name sample-http \
  --source-uri https://example.com/data.json
```

## Runtime configuration

All tasks use environment variables prefixed with `PIPELINE_` (MinIO, PostgreSQL,
Milvus, ChromaDB, source credentials). Kubernetes secrets in
`kubernetes/mlops/pipelines/` provide the in-cluster defaults.

