# Cross-repo lineage bridge

The `agentic_assistants` repository maintains a shared lineage graph
(dataset → run → model → report). AQP publishes events to the same
service via
[`aqp.mlops.lineage_bridge`](../../aqp/mlops/lineage_bridge.py) so both
repos present a unified view in the Lineage UI.

## Configuration

Set `AQP_AGENTIC_ASSISTANTS_API` in the environment (or in the k8s
ConfigMap `aqp-env`):

```bash
export AQP_AGENTIC_ASSISTANTS_API=http://agentic-assistants.aqp.svc.cluster.local:8000
```

When the setting is empty the bridge is a no-op — every `emit_*` call
logs at DEBUG and returns `False`.

## Emitting events

```python
from aqp.mlops import (
    emit_dataset, emit_run, emit_model, emit_serve_deployment
)

# 1. Record the training dataset.
emit_dataset("abc123def", n_rows=2_000_000, n_symbols=500)

# 2. Log a training run tied to that dataset.
emit_run("run-42", kind="alpha_training", dataset_hash="abc123def",
         model_class="LightGBMAlpha")

# 3. Register the resulting model artifact.
emit_model("aqp-alpha", version="7", run_id="run-42",
           metrics={"ic_mean": 0.042})

# 4. Record the live deployment serving it.
emit_serve_deployment(
    endpoint_url="http://ray-serve.aqp.svc.cluster.local:8000/aqp",
    backend="ray-serve",
    model_uri="models:/aqp-alpha/Production",
)
```

## Event schema

Each event is a JSON POST to `/api/lineage/events`:

```json
{
  "kind": "model",
  "id": "model:aqp-alpha/7",
  "attrs": { "run_id": "run-42", "metrics": { "ic_mean": 0.042 } },
  "parents": ["run:run-42"]
}
```

## Retention

Events live in the `agentic_assistants` lineage store (Postgres).
Retention matches that project's settings (default 90 days for
`run` / `serve_deployment`, indefinite for `dataset` / `model`).
