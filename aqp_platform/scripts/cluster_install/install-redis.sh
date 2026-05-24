#!/usr/bin/env bash
# =============================================================================
# Install / Reconcile Redis 8 Stack
# =============================================================================
# Applies kubernetes/base-services/redis/, waits for the Deployment to roll
# out, then runs a smoke test (PING + MODULE LIST + FT._LIST) so failures
# surface immediately instead of after the next consumer tries to connect.
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - data-services namespace exists
#
# Usage:
#   bash bootstrap/scripts/install-redis.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REDIS_KUSTOMIZE_DIR="${REPO_ROOT}/kubernetes/base-services/redis"
NS="data-services"

echo "==> Applying Redis Stack manifests from ${REDIS_KUSTOMIZE_DIR}"
kubectl apply -k "${REDIS_KUSTOMIZE_DIR}"

echo "==> Waiting for redis Deployment to become Ready (timeout 5m)"
kubectl -n "${NS}" rollout status deployment/redis --timeout=5m

echo "==> Waiting for redis-exporter Deployment to become Ready (timeout 2m)"
kubectl -n "${NS}" rollout status deployment/redis-exporter --timeout=2m

echo "==> Smoke test: PING"
PASSWORD="$(kubectl -n "${NS}" get secret redis-credentials -o jsonpath='{.data.password}' | base64 -d)"
PONG="$(kubectl -n "${NS}" exec deploy/redis -- \
    redis-cli -a "${PASSWORD}" --no-auth-warning ping || true)"
if [[ "${PONG}" != "PONG" ]]; then
    echo "ERROR: redis ping returned '${PONG}' instead of 'PONG'"
    exit 1
fi
echo "    -> PING OK"

echo "==> Smoke test: MODULE LIST"
MODULES_RAW="$(kubectl -n "${NS}" exec deploy/redis -- \
    redis-cli -a "${PASSWORD}" --no-auth-warning MODULE LIST | tr -d '\r')"
echo "${MODULES_RAW}"
for required in search ReJSON timeseries bf; do
    if ! grep -iq "${required}" <<<"${MODULES_RAW}"; then
        echo "ERROR: required Redis module '${required}' not loaded"
        exit 1
    fi
done
echo "    -> All required modules present (search, ReJSON, timeseries, bf)"

echo "==> Smoke test: FT._LIST"
FT_LIST="$(kubectl -n "${NS}" exec deploy/redis -- \
    redis-cli -a "${PASSWORD}" --no-auth-warning FT._LIST 2>/dev/null || true)"
echo "    indexes: ${FT_LIST:-<none yet, expected on first install>}"

echo "==> Smoke test: redis_exporter /metrics"
EXPORTER_POD="$(kubectl -n "${NS}" get pod -l app=redis-exporter -o jsonpath='{.items[0].metadata.name}')"
if ! kubectl -n "${NS}" exec "${EXPORTER_POD}" -- wget -qO- http://localhost:9121/metrics | head -n 5; then
    echo "ERROR: redis-exporter /metrics endpoint did not respond"
    exit 1
fi
echo "    -> exporter OK"

echo "==> Done. Redis 8 Stack is ready."
echo "    Service:        redis.${NS}.svc.cluster.local:6379"
echo "    RAGFlow alias:  ragflow-redis.${NS}.svc.cluster.local:6379"
echo "    Exporter:       redis-exporter.${NS}.svc.cluster.local:9121"
echo "    Password secret: ${NS}/redis-credentials (key=password)"
