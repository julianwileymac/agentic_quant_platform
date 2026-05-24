# rpi_k8s_sdk (deprecated)

Status: **archived rollback helper** — moved from `rpi_kubernetes/management/sdk/`.

New cluster automation MUST use:

- [`aqp_cli`](../../../aqp_cli/) for operator CLI flows
- [`AQPControlPlaneClient`](../../../aqp/services/control_plane_client.py) for
  `/manage/*` HTTP calls

Legacy clients in this package (`MinioClient`, `MLflowClient`, in-cluster Kafka
admin, etc.) assumed shared services lived in the rpi repo. Those services now
deploy from `aqp_platform/deployments/kubernetes/`.

Smoke test (optional):

```bash
python -m pytest aqp_platform/rollback/rpi_k8s_sdk/tests
```
