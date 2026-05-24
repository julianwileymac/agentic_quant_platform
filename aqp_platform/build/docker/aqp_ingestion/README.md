# build/docker/aqp_ingestion

GDelt + BigQuery + Alpha Vantage + regulatory ingestion image. Today these tasks run on `aqp_worker`; the split exists so heavy ingestion deps (`gcsfs`, `pyarrow`, `bigquery-storage`) can be kept out of the main worker image when needed.

## When to use this image instead of `aqp_worker`

- Dedicated ingestion workloads that need a different resource profile (large memory, slow disk) than the ML training workloads
- Tenant isolation — separate Celery worker pool for the ingestion queue means a runaway ingestion job can't starve agent / backtest tasks
- Region-pinned ingestion — when the BigQuery client must run in a specific GCP region for free-tier egress

## Queues

| Queue        | Tasks                                                |
| ------------ | ---------------------------------------------------- |
| `ingestion`  | `aqp.tasks.ingest_tasks`, `aqp.tasks.dataset_preset_tasks` |
| `regulatory` | `aqp.tasks.regulatory_tasks`                          |
| `streaming`  | `aqp.tasks.streaming_link_tasks`                      |

## Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file build/docker/aqp_ingestion/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-ingestion:dev \
  .
```
