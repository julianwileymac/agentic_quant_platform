# build/docker/aqp_worker

Celery worker image consuming `aqp.tasks.*` queues. Single-stage `python:3.11-slim` build because the worker needs the full `aqp` runtime including heavy ML / RL deps.

Queues this image handles:

| Queue            | Tasks                                                                   |
| ---------------- | ----------------------------------------------------------------------- |
| `default`        | Bookkeeping, lineage events, low-priority maintenance                   |
| `backtest`       | Backtest engine runs (vbtpro, event-driven, hftbacktest)                |
| `agents`         | `AgentRuntime`-driven LangGraph + CrewAI tasks                          |
| `ingestion`      | Data ingestion pipelines (handled by `aqp_ingestion` image when split)  |
| `training`       | ML / RL training runs                                                   |
| `paper`          | Paper-trading session loop                                              |
| `terraform`      | TerraformRuntime apply / destroy / plan                                 |
| `workflows`      | `WorkflowRuntime` driven orchestration                                  |

## Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file build/docker/aqp_worker/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-worker:dev \
  .
```

## Scaling

The aqp-worker image is HPA-eligible. The autoscaler target is custom Celery queue depth via `aqp.observability.metrics.celery_queue_depth`. See `/deployments/kubernetes/base/aqp-worker/hpa.yaml`.
