---
title: 'Kubernetes deployment'
summary: 'The [`Dockerfile`](../../Dockerfile) builds five targets:'
owner: ml-team
last_reviewed: 2026-05-25
audience: both
---

# Kubernetes deployment

AQP ships Kustomize manifests under [`aqp_platform/deploy/k8s/base/`](../../aqp_platform/deploy/k8s/base/)
that can be applied to any cluster. The manifests under `base/serving/`
add three model-serving backends on top of the existing `api`, `worker`,
`paper-trader`, and streaming-ingester Deployments.

## Image targets

The [`Dockerfile`](../../Dockerfile) builds five targets:

| Target | Entrypoint | Used by |
| --- | --- | --- |
| `base` | — | shared base layer |
| `paper` | `aqp paper run` | `paper-trader.yaml` |
| `ingester` | `aqp-stream-ingest` | `ingester-*.yaml` |
| `api` (default) | `uvicorn aqp.api.main:app` | `api.yaml`, `worker.yaml` |
| `serving` | `aqp serve <backend>` | `serving/*.yaml` |
| `ml-train` | `aqp-train` | CI training jobs, Ray Tune sweeps |

Build all five at once:

```bash
for target in paper ingester api serving ml-train; do
  docker build --target "$target" -t "aqp-${target}:latest" .
done
```

## Deploying to a Kubernetes cluster

AQP is cluster-agnostic. The `aqp_platform/deployments/kubernetes/` tree provisions
every shared dependency (MLflow in `aqp-mlops`, MinIO + Postgres + Redis
+ ChromaDB in `aqp-data-services`, Kafka + Schema Registry + Flink in
`aqp-streaming`, kube-prometheus-stack + Tempo + Loki + OTel + Phoenix
in `aqp-observability`, and so on). To deploy AQP:

```bash
# From the agentic_quant_platform root
# 1. Install the operators / Helm releases that AQP CRDs depend on.
bash aqp_platform/scripts/cluster_install/install-redpanda.sh
bash aqp_platform/scripts/cluster_install/install-kube-prometheus-stack.sh
bash aqp_platform/scripts/cluster_install/install-opentelemetry-operator.sh
bash aqp_platform/scripts/cluster_install/install-spark-operator.sh
bash aqp_platform/scripts/cluster_install/install-flink.sh

# 2. Apply the AQP base kustomization (creates aqp-* namespaces and
#    the workload manifests).
kubectl apply -k aqp_platform/deployments/kubernetes/base/
```

## Selecting which model to serve

The three serving backends all read a single `model_uri` from the
`aqp-serving-env` ConfigMap. Change it once and bounce the Deployments:

```bash
kubectl -n aqp create configmap aqp-serving-env \
  --from-literal=model_uri=models:/aqp-alpha/Production \
  --from-literal=ray_serve_name=aqp-alpha \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n aqp rollout restart deploy mlflow-serve ray-serve torchserve
```

## Observability

- Every Deployment exports traces to `http://otel-collector:4317`
  (OTLP gRPC), matching the `rpi_kubernetes` collector conventions.
- Prometheus picks up metrics via the `ServiceMonitor` resources in
  [`aqp_platform/deploy/k8s/base/serving/servicemonitor.yaml`](../../aqp_platform/deploy/k8s/base/serving/servicemonitor.yaml).
- AQP's own metric surface is defined in
  [`aqp/mlops/metrics.py`](../../aqp/mlops/metrics.py):
  `aqp_train_duration_seconds`, `aqp_backtest_sharpe`, `aqp_paper_pnl`,
  `aqp_serve_requests_total`, `aqp_serve_latency_seconds`.

## Secrets

The `aqp-broker-secrets` Secret supplies Alpaca / IBKR / Tradier
credentials. For the serving stack no secrets are required unless the
MLflow tracking URI needs auth — set `MLFLOW_TRACKING_TOKEN` in
`aqp-env` or a dedicated Secret.
