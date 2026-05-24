# Legacy management rollback shell (archived)

Status: **rollback-only** — opt-in emergency revert when `aqp_control_plane` is
unavailable.

Source for the deprecated `rpi-k8s-management` API and `rpi-k8s-control-panel` UI
was moved here from `rpi_kubernetes/management/` during the rpi ↔ AQP decoupling.
Images stay pinned to `:v1-final`; do not advance tags.

## Kubernetes apply

```bash
# From agentic_quant_platform repo root
kubectl apply -k aqp_platform/deployments/kubernetes/rollback/legacy-management/
```

## When to use

Apply only when the AQP control plane (`aqp-cp`, `https://manage.aqp.fund`) is down
and you need the legacy `/api/{kafka,flink,alphavantage,redis,mlflow,observability}/*`
paths until service is restored.

## Replacement surface

| Legacy | Canonical |
| --- | --- |
| `/api/kafka/*`, `/api/flink/*` | `aqp_control_plane` `/manage/streaming/*` |
| `/api/cluster/*` | `/manage/topology/*` |
| Operator UI | `aqp_client` admin routes |

See [aqp_platform/deployments/kubernetes/rollback/legacy-management/README.md](../deployments/kubernetes/rollback/legacy-management/README.md).
