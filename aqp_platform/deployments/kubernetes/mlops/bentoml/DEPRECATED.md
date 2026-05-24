# DEPRECATED: BentoML / Yatai

> **As of 2026-Q2 the BentoML/Yatai control plane is deprecated on the
> rpi_kubernetes platform.  Use [KServe](../kserve/) instead.**

## Why

* The upstream open-source `bentoml/yatai` chart has been effectively
  abandoned - the last release was `1.0.0` (mid-2022).  BentoCloud (the
  paid SaaS) absorbed all subsequent development.
* The chart has not been updated for current Postgres / MinIO / Kubernetes
  versions and shipped with default credentials that are unsafe to leave
  in place.
* KServe is the upstream-supported, vendor-neutral standard for serving
  ML models on Kubernetes.  It is already wired into the platform under
  [`../kserve/`](../kserve/).

## What replaces it

| BentoML/Yatai concept            | KServe equivalent                                      |
| -------------------------------- | ------------------------------------------------------ |
| Bento (packaged model + runtime) | KServe `InferenceService` referencing an `s3://` URI   |
| Yatai web UI                     | Management console `/services` page + Grafana panels   |
| Bento storage                    | MinIO `model-registry` / `mlflow-artifacts` buckets    |
| Yatai Postgres metadata          | MLflow registry + Argo Workflows runs                  |

See [`../kserve/install/README.md`](../kserve/install/README.md) for the
KServe install procedure and
[`../kserve/inferenceservice-mlflow-example.yaml`](../kserve/inferenceservice-mlflow-example.yaml)
for an end-to-end MLflow-backed serving example.

## Why this folder still exists

* Git history of the previous deployment remains intact.
* Anyone with an existing Yatai Helm release still installed in the
  cluster can keep `kubectl apply -f kubernetes/mlops/bentoml/secret.yaml`
  working manually.
* The folder is no longer included by the root `kubernetes/kustomization.yaml`,
  so a clean `kubectl apply -k kubernetes/` will not provision Yatai.

If you want to fully remove the legacy install:

```bash
helm uninstall yatai -n ml-platform || true
kubectl delete -k kubernetes/mlops/bentoml/ || true
```
