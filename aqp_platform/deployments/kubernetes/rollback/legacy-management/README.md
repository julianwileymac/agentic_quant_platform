# legacy-management — rollback-only Kubernetes manifests

Status: **rollback-only**. Default AQP rollout does **not** apply this kustomization.

Moved from `rpi_kubernetes/kubernetes/base-services/management/` and
`rpi_kubernetes/kubernetes/legacy-management/` during the rpi ↔ AQP decoupling.

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/rollback/legacy-management/
```

Rollback source trees live under `aqp_platform/rollback/legacy-management/`.
The deprecated Python SDK lives under `aqp_platform/rollback/rpi_k8s_sdk/` — prefer
`aqp_cli` and `AQPControlPlaneClient` for new work.
