# Loki - Log Aggregation System

Loki is a horizontally scalable, highly available log aggregation system inspired by Prometheus.

## Installation

```bash
# Add Grafana Helm repository
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Create/refresh MinIO credentials used by Loki chart values
kubectl apply -f kubernetes/observability/loki/minio-secret.yaml

# Install or upgrade Loki
helm upgrade --install loki grafana/loki \
  --namespace observability \
  --create-namespace \
  -f values.yaml
```

## Configuration

This deployment uses:
- **Single Binary Mode**: Appropriate for the RPi cluster size
- **MinIO Object Storage**: `loki-data` bucket in `minio.aqp-data-services.svc.cluster.local:9000`
- **30-day Retention**: Configurable in `values.yaml`
- **OpenTelemetry Collector Export**: Logs are pushed via Loki HTTP API (`/loki/api/v1/push`)

`loki-data` is created automatically by the MinIO bootstrap job in `kubernetes/base-services/minio/bootstrap-buckets-job.yaml`.

## Access

After installation, Loki is accessible at:
- **Internal**: `http://loki.observability:3100`
- **External**: `http://loki.local` (via Ingress)

## Integration with Grafana

Loki is automatically configured as a datasource in Grafana. You can query logs using LogQL:

```logql
{namespace="ml-platform"} |= "error"
```

## OpenTelemetry Integration

The OpenTelemetry Collector is configured to export logs to Loki using Loki's push API endpoint.
With the collector `filelog` receiver enabled, Kubernetes pod logs are collected from node log files and forwarded to Loki.

## Retention

Logs are retained for 30 days by default. To adjust retention, modify the `retention_period` in `values.yaml`.
