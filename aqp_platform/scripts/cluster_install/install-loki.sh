#!/usr/bin/env bash
# =============================================================================
# Install or upgrade Grafana Loki (MinIO S3 backend) in observability namespace
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VALUES="$REPO_ROOT/kubernetes/observability/loki/values.yaml"
NS="${LOKI_NAMESPACE:-observability}"

echo "==> Ensuring Grafana Helm repo"
helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
helm repo update grafana

echo "==> Creating MinIO buckets for Loki (data-services)"
kubectl exec -n aqp-data-services deploy/minio -- \
  sh -c 'mc alias set local http://127.0.0.1:9000 minioadmin minioadmin123 && \
         mc mb local/loki-chunks --ignore-existing && \
         mc mb local/loki-ruler --ignore-existing'

echo "==> Installing / upgrading Loki"
helm upgrade --install loki grafana/loki \
  --namespace "$NS" \
  --create-namespace \
  -f "$VALUES"

echo "==> Done. Loki query API: http://loki.${NS}:3100 (in-cluster)"
