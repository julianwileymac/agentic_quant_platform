#!/usr/bin/env bash
# install-questdb.sh — QuestDB bootstrap for AQP tick/quote/execution storage.
# Idempotent: reruns reconcile the same manifests and secret.
set -euo pipefail

NAMESPACE="${QUESTDB_NAMESPACE:-aqp-timeseries}"
PG_PASSWORD="${QUESTDB_PG_PASSWORD:-aqp}"
KUSTOMIZE_PATH="${QUESTDB_KUSTOMIZE_PATH:-$(dirname "$0")/../../deployments/kubernetes/base-services/questdb}"

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Secret is optional in the StatefulSet, but create it for a predictable PGWire
# auth path in dev and shared environments.
kubectl -n "${NAMESPACE}" create secret generic questdb-credentials \
  --from-literal=pg-password="${PG_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -k "${KUSTOMIZE_PATH}"

kubectl -n "${NAMESPACE}" rollout status statefulset/questdb --timeout="${QUESTDB_ROLLOUT_TIMEOUT:-600s}"

echo "QuestDB installed: namespace=${NAMESPACE}"
echo "  HTTP:    http://questdb.${NAMESPACE}.svc.cluster.local:9000"
echo "  ILP TCP: questdb.${NAMESPACE}.svc.cluster.local:9009"
echo "  PGWire:  questdb.${NAMESPACE}.svc.cluster.local:8812"
