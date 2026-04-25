# Model serving

AQP ships three serving adapters. All three share the same
[`ModelDeployment`](../../aqp/mlops/serving/base.py) protocol so
call-sites, the CLI (`aqp serve ...`), and the REST API speak one
vocabulary regardless of the runtime underneath.

| Backend | Adapter | CLI | Best for |
| --- | --- | --- | --- |
| MLflow Models | [`MLflowServeDeployment`](../../aqp/mlops/serving/mlflow_serve.py) | `aqp serve mlflow <uri>` | any flavor logged with `mlflow.log_model`, low-throughput research |
| Ray Serve | [`RayServeDeployment`](../../aqp/mlops/serving/ray_serve.py) | `aqp serve ray <uri>` | horizontally scaled batch inference |
| TorchServe | [`TorchServeDeployment`](../../aqp/mlops/serving/torchserve.py) | `aqp serve torchserve <uri>` | low-latency PyTorch endpoints + batching |

## Model URIs

All adapters accept three URI shapes:

1. **Filesystem path** — `./data/models/alpha_v1.pkl`
2. **MLflow run** — `runs:/<run-id>/<artifact>`
3. **MLflow registry** — `models:/<name>/<stage>` or `models:/<name>/<version>`

MLflow URIs are resolved via `aqp.mlops.serving.base.resolve_model`, which
optionally downloads the artifact locally when a backend needs filesystem
access (TorchServe packaging) or passes the URI through (MLflow Serve).

## PreprocessingSpec propagation

Every adapter honours the
[`PreprocessingSpec`](../architecture/preprocessing-spec.md) attached to
the model. At inference time:

- **MLflow Serve** — flavor-specific (`pyfunc` handlers are expected to
  re-apply preprocessing inside the model class).
- **Ray Serve** — the generated deployment loads the pickle and delegates
  to `model.predict(df)`; when `model.preprocessing_spec` is set, the
  `apply` call happens in `__call__` before `predict`.
- **TorchServe** — the auto-generated `AqpBaseHandler` checks for a
  `preprocessing_spec` attribute and runs `spec.apply(df)` before every
  call.

## Quick start

```bash
# Train something and log to MLflow
python scripts/train_agent.py --config configs/ml/lgbm.yaml

# Serve the latest production version via MLflow
aqp serve mlflow models:/aqp-lgbm/Production --port 5001

# Or via Ray Serve
aqp serve ray models:/aqp-lgbm/Production --num-replicas 4

# Or package for TorchServe
aqp serve torchserve models:/aqp-lstm/Production --model-name aqp-lstm
```

## Kubernetes

Manifests and Helm values for deploying each backend to the
`rpi_kubernetes` cluster live under `deploy/kubernetes/serving/` and are
described in [`docs/mlops/k8s-deployment.md`](./k8s-deployment.md)
(Phase 5).
