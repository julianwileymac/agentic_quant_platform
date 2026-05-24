# Dagster - Data Orchestration Platform

Dagster provides data and ML orchestration with a web UI, scheduler/daemon, and Kubernetes-native run launcher.

## Installation

```bash
# Add Dagster Helm repository
helm repo add dagster https://dagster-io.github.io/helm
helm repo update

# Ensure Dagster baseline secret/config exist
kubectl apply -k .

# Install or upgrade Dagster
helm upgrade --install dagster dagster/dagster \
  --namespace mlops \
  --create-namespace \
  -f values.yaml \
  --set postgresql.postgresqlHost="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.host}' | base64 -d)" \
  --set postgresql.service.port="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.port}' | base64 -d)" \
  --set postgresql.postgresqlDatabase="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.database}' | base64 -d)" \
  --set postgresql.postgresqlUsername="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.user}' | base64 -d)" \
  --set postgresql.postgresqlPassword="$(kubectl get secret -n mlops dagster-postgresql -o jsonpath='{.data.password}' | base64 -d)"

# Wait for webserver to become ready
kubectl rollout status deployment/dagster-dagster-webserver -n mlops --timeout=240s
```

## Access

After installation, Dagster UI is accessible at:
- **Internal**: `http://dagster-dagster-webserver.mlops`
- **External**: `http://dagster.local` (via Ingress)

## Verification

```bash
# Check runtime components
kubectl get deploy -n mlops | grep dagster
kubectl get pods -n mlops | grep dagster

# Check ingress and service
kubectl get ingress -n mlops
kubectl get svc -n mlops | grep dagster

# Validate database connectivity from Dagster pods
kubectl logs -n mlops deploy/dagster-dagster-webserver --tail=100
```

`values.yaml` deploys a baseline reachable Dagster UI with `dagsterDaemon` disabled.
When you enable pipeline user-code via `values-pipelines-user-code.yaml`, daemon/scheduler
processing is enabled as part of that override.

## Observability Integration

- Dagster pods are configured with OTLP environment variables to emit telemetry to:
  `otel-collector.observability.svc.cluster.local:4317`
- Compute logs are configured for MinIO (`dagster-artifacts` bucket).
- Add dashboards/queries in Grafana based on Dagster-emitted telemetry and application metrics.

## User Code Deployments

`values.yaml` includes a lightweight example user-code deployment
(`docker.io/dagster/user-code-example`) so the webserver boots with a valid workspace.

To run in-repo pipeline assets, build/push the pipeline image and apply the
`values-pipelines-user-code.yaml` override:

```bash
docker build -f ../../../pipelines/Dockerfile -t ghcr.io/julianwiley/rpi-k8s-pipelines:latest ../../..
docker push ghcr.io/julianwiley/rpi-k8s-pipelines:latest

helm upgrade --install dagster dagster/dagster \
  --namespace mlops \
  --create-namespace \
  -f values.yaml \
  -f values-pipelines-user-code.yaml
```

Implemented assets are defined in:
`pipelines/dagster_user_code/definitions.py`

- `minio_to_postgres_curated`
- `vectorize_to_milvus_chroma`
- `cdc_incremental_sync`
- `hybrid_argo_heavy_transform`

### Production hardening TODO

1. Pin user-code image to immutable digest.
2. Externalize source/sink credentials via secret manager.
3. Add asset checks and data quality contracts.

## Troubleshooting

If Dagster is unavailable, run:

```bash
# Detect missing Helm release
helm list -n mlops | grep dagster

# Re-install with repo values
kubectl apply -k .
helm upgrade --install dagster dagster/dagster \
  --namespace mlops \
  --create-namespace \
  -f values.yaml

# Verify webserver service + ingress
kubectl get svc -n mlops dagster-dagster-webserver
kubectl get ingress -n mlops dagster-ingress
kubectl get pods -n mlops | grep dagster

# If logs show postgres auth failures for user dagster, reconcile DB credentials
kubectl exec -n data-services deploy/postgresql -- psql -U postgres -d postgres -c "ALTER ROLE dagster WITH LOGIN PASSWORD 'dagster123';"
```
