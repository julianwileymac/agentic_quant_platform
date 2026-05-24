#!/usr/bin/env bash
set -euo pipefail

# verify_tower_cluster.sh
# Smoke checks for the two-node tower+laptop AQP cluster.

TOWER_NODE="${TOWER_NODE:-aqp-tower}"
LAPTOP_NODE="${LAPTOP_NODE:-aqp-laptop}"
NAMESPACE_APP="${NAMESPACE_APP:-aqp}"
NAMESPACE_ADMIN="${NAMESPACE_ADMIN:-aqp-admin}"
NAMESPACE_TIMESERIES="${NAMESPACE_TIMESERIES:-aqp-timeseries}"
TIMEOUT="${VERIFY_TIMEOUT_SECONDS:-180}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required." >&2
  exit 1
fi

echo "[verify] nodes"
kubectl get nodes

echo "[verify] expecting ${TOWER_NODE} + ${LAPTOP_NODE} Ready"
kubectl wait --for=condition=Ready "node/${TOWER_NODE}" --timeout="${TIMEOUT}s"
kubectl wait --for=condition=Ready "node/${LAPTOP_NODE}" --timeout="${TIMEOUT}s"

echo "[verify] namespaces"
kubectl get ns "${NAMESPACE_APP}" "${NAMESPACE_ADMIN}" "${NAMESPACE_TIMESERIES}" >/dev/null

echo "[verify] core deployments"
kubectl -n "${NAMESPACE_APP}" rollout status deploy/aqp-core --timeout="${TIMEOUT}s"
kubectl -n "${NAMESPACE_APP}" rollout status deploy/aqp-worker --timeout="${TIMEOUT}s"
kubectl -n "${NAMESPACE_APP}" rollout status deploy/aqp-client --timeout="${TIMEOUT}s"
kubectl -n "${NAMESPACE_ADMIN}" rollout status deploy/aqp-cp --timeout="${TIMEOUT}s"

echo "[verify] stateful services"
kubectl -n "${NAMESPACE_APP}" rollout status statefulset/redis-master --timeout="${TIMEOUT}s"
kubectl -n "${NAMESPACE_TIMESERIES}" rollout status statefulset/questdb --timeout="${TIMEOUT}s"

echo "[verify] questdb service endpoints"
QUESTDB_ENDPOINTS="$(kubectl -n "${NAMESPACE_TIMESERIES}" get endpoints questdb -o jsonpath='{.subsets[*].addresses[*].ip}')"
if [[ -z "${QUESTDB_ENDPOINTS}" ]]; then
  echo "questdb service has no ready endpoints" >&2
  exit 1
fi

echo "[verify] cluster smoke checks passed."
