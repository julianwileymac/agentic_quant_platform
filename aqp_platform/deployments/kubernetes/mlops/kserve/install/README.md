# KServe Controller Installation

KServe is the **primary model-serving plane** for the rpi_kubernetes platform.
It replaces the previous Yatai/BentoML control plane (now deprecated, see
`kubernetes/mlops/bentoml/DEPRECATED.md`).

The controller itself is installed via Helm because the upstream chart owns
the CRDs and the operator deployment.  This directory only holds the chart
values and the install script.

## Prerequisites

* `cert-manager` already installed in the cluster (KServe needs it for the
  webhook certificates).
* MinIO bootstrap job has run (creates the `model-registry` and
  `model-cache` buckets and provisions the `svc-models` user).

## Install or upgrade

```bash
# 1. CRDs (idempotent)
kubectl apply -f https://github.com/kserve/kserve/releases/download/v0.13.0/kserve.yaml

# 2. Controller chart with our overrides
helm upgrade --install kserve oci://ghcr.io/kserve/charts/kserve \
  --version v0.13.0 \
  --namespace kserve \
  --create-namespace \
  -f ../values-kserve.yaml
```

After install, the `serving.kserve.io/v1beta1.InferenceService` API is
available in every namespace.  See `../inferenceservice-mlflow-example.yaml`
for an end-to-end example backed by an MLflow-registered model.

## Wired up to observability

* The vLLM Deployments under `..` are annotated with
  `prometheus.io/scrape: "true"` so the kube-prometheus-stack scrapes them
  out of the box.
* The `kserve-controller-manager` is covered by a dedicated ServiceMonitor
  in `kubernetes/observability/prometheus/servicemonitors.yaml`.
* All vLLM pods have `OTEL_EXPORTER_OTLP_ENDPOINT` pointing at the
  in-cluster collector for trace export.
