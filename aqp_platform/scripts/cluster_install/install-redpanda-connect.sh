#!/usr/bin/env bash
# install-redpanda-connect.sh — Redpanda Connect pipelines for QuestDB sinks.
# Idempotent: reruns reconcile deployment/config/service and wait for readiness.
set -euo pipefail

NAMESPACE="${REDPANDA_CONNECT_NAMESPACE:-aqp-streaming}"
KUSTOMIZE_PATH="${REDPANDA_CONNECT_KUSTOMIZE_PATH:-$(dirname "$0")/../../aqp_platform/deployments/kubernetes/base-services/redpanda-connect}"

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -k "${KUSTOMIZE_PATH}"
kubectl -n "${NAMESPACE}" rollout status deployment/redpanda-connect --timeout="${REDPANDA_CONNECT_ROLLOUT_TIMEOUT:-600s}"

echo "Redpanda Connect installed: namespace=${NAMESPACE}"
echo "  Pipelines ConfigMap: redpanda-connect-pipelines"
