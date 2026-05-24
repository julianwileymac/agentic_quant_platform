#!/usr/bin/env bash
# install-phoenix.sh — Self-hosted Arize Phoenix + Postgres backend.
# Phase 2d of the AQP infra-expansion plan.
set -euo pipefail

NAMESPACE="${PHOENIX_NAMESPACE:-aqp-observability}"
PHOENIX_PASSWORD="${PHOENIX_PASSWORD:-}"

if [[ -z "${PHOENIX_PASSWORD}" ]]; then
  echo "ERROR: set PHOENIX_PASSWORD before running install-phoenix.sh"
  exit 1
fi

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

PHOENIX_DSN="postgresql://phoenix:${PHOENIX_PASSWORD}@phoenix-postgresql.${NAMESPACE}.svc.cluster.local:5432/phoenix"
kubectl -n "${NAMESPACE}" create secret generic phoenix-db-secret \
  --from-literal=url="${PHOENIX_DSN}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${NAMESPACE}" create secret generic phoenix-postgresql \
  --from-literal=password="${PHOENIX_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -k "$(dirname "$0")/../../aqp_platform/deployments/kubernetes/observability/phoenix/"

echo "Phoenix installed: namespace=${NAMESPACE}"
