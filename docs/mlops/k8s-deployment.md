# Kubernetes deployment

AQP ships Kustomize manifests under [`deploy/k8s/base/`](../../deploy/k8s/base/)
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

## Deploying to `rpi_kubernetes`

The cluster at `C:/Users/.../rpi_kubernetes` is already wired with
MLflow (`mlops` namespace), MinIO (`data-services`), Redis, Kafka,
Prometheus, and OTel Collector. To deploy AQP:

```bash
# From the agentic_quant_platform root
kubectl create namespace aqp --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -k deploy/k8s/base/
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
  [`deploy/k8s/base/serving/servicemonitor.yaml`](../../deploy/k8s/base/serving/servicemonitor.yaml).
- AQP's own metric surface is defined in
  [`aqp/mlops/metrics.py`](../../aqp/mlops/metrics.py):
  `aqp_train_duration_seconds`, `aqp_backtest_sharpe`, `aqp_paper_pnl`,
  `aqp_serve_requests_total`, `aqp_serve_latency_seconds`.

## Secrets

The `aqp-broker-secrets` Secret supplies Alpaca / IBKR / Tradier
credentials. For the serving stack no secrets are required unless the
MLflow tracking URI needs auth — set `MLFLOW_TRACKING_TOKEN` in
`aqp-env` or a dedicated Secret.
