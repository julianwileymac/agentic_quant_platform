# Kubernetes deployment

Kustomize-based manifests for running the agentic quant platform in a
Kubernetes cluster. The paper-trading deployment is the primary
motivator — it runs as a single-replica Deployment with `Recreate`
strategy so stateful broker sessions never race.

## Layout

```
deploy/k8s/
├── base/                   # environment-agnostic resources
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── redis.yaml
│   ├── postgres.yaml
│   ├── otel-collector.yaml
│   ├── jaeger.yaml
│   ├── api.yaml
│   ├── worker.yaml
│   ├── beat-deployment.yaml   # Phase 5 — Celery beat singleton + FinOps RBAC
│   ├── paper-trader.yaml
│   ├── ibgateway.yaml         # in-cluster IB Gateway for the streaming pipeline
│   ├── ingester-ibkr.yaml     # 24/7 IBKR -> Kafka ingester
│   ├── ingester-alpaca.yaml   # 24/7 Alpaca -> Kafka ingester
│   └── kustomization.yaml
└── overlays/
    ├── dev/                # debug-level sampling, single worker
    └── prod/               # reduced sampling, 2 workers
```

## FinOps governance (Phase 5)

The `kustomization.yaml` `commonLabels` block stamps four mandatory tags on
every resource:

| Label | Source | Default |
| --- | --- | --- |
| `project` | `AQP_PROJECT_TAG` / `Settings.project_tag` | `aqp-default` |
| `cost_center` | `AQP_COST_CENTER` / `Settings.cost_center` | `quant-research-01` |
| `owner` | `AQP_OWNER` / `Settings.owner` | `system-orchestrator` |
| `data_classification` | `AQP_DATA_CLASSIFICATION` / `Settings.data_classification` | `proprietary-alpha` |

The Kyverno [`require-finops-tags` ClusterPolicy](../../../rpi_kubernetes/kubernetes/policies/finops/require-finops-tags.yaml)
in `rpi_kubernetes` enforces these as `validationFailureAction: Enforce` —
any Pod / Job / CronJob / Deployment / StatefulSet missing one is denied at
admission time.

The `aqp-beat` singleton in `beat-deployment.yaml` runs the
[`aqp.tasks.finops_tasks.audit`](../../aqp/tasks/finops_tasks.py) task every
6 hours as a backstop in case the policy is bypassed (e.g. a Helm chart
that pre-dates this repo). The accompanying ClusterRole grants the beat
ServiceAccount read-only access to Pods / Jobs / CronJobs / Deployments
cluster-wide so the scan can attribute every workload back to a strategy
or agent run.

## Build + push images

```bash
# Default API + worker image
docker build -t aqp:latest .

# Paper trader (multi-stage target)
docker build --target paper -t aqp-paper:latest .

# Streaming ingester (multi-stage target -- runs aqp-stream-ingest)
docker build --target ingester -t aqp-ingester:latest .

# Push to your registry and update kustomization.yaml ``images:`` fields
docker tag aqp:latest ghcr.io/your-org/aqp:latest
docker tag aqp-paper:latest ghcr.io/your-org/aqp-paper:latest
docker tag aqp-ingester:latest ghcr.io/your-org/aqp-ingester:latest
docker push ghcr.io/your-org/aqp:latest
docker push ghcr.io/your-org/aqp-paper:latest
docker push ghcr.io/your-org/aqp-ingester:latest
```

## Apply

```bash
# Dev namespace
kubectl apply -k deploy/k8s/overlays/dev

# Prod namespace
kubectl apply -k deploy/k8s/overlays/prod
```

## Populate broker credentials

```bash
kubectl -n aqp-dev create secret generic aqp-broker-secrets \
  --from-literal=AQP_ALPACA_API_KEY=... \
  --from-literal=AQP_ALPACA_SECRET_KEY=... \
  --from-literal=AQP_TRADIER_TOKEN=... \
  --from-literal=AQP_TRADIER_ACCOUNT_ID=... \
  --from-literal=TWS_USERID=...         `# IB Gateway login (optional)` \
  --from-literal=TWS_PASSWORD=...
```

Once the secret exists, flip `dry_run: true` → `false` in the
`aqp-paper-config` ConfigMap and redeploy the `paper-trader` Deployment.

## Streaming platform

The `ingester-ibkr`, `ingester-alpaca`, and `ibgateway` Deployments
connect to the Kafka cluster deployed by the companion
`rpi_kubernetes` repo. The configmap default
``AQP_KAFKA_BOOTSTRAP=trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9092``
assumes both workloads live in the same cluster. Override it in an
overlay to point at an external Kafka.

See [../../docs/streaming.md](../../docs/streaming.md) for the full
ingester + Flink + KafkaDataFeed architecture.

## Observability

Jaeger is forwarded locally with:

```bash
kubectl -n aqp-dev port-forward svc/jaeger 16686:16686
```

Then visit [http://localhost:16686](http://localhost:16686).

## Notes

- Redis + Postgres in-cluster are minimal dev conveniences; production
  deployments should use managed services (ElastiCache / RDS, Cloud
  Memorystore / Cloud SQL, …) and remove those resources from `base/`.
- The `api` Deployment serves the Solara UI + Dash mount on port 8000;
  expose it via your Ingress controller of choice.
