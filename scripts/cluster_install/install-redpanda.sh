#!/usr/bin/env bash
# install-redpanda.sh — Redpanda operator + Redpanda CR (side-by-side
# with Strimzi Kafka per the AQP infra-expansion plan, question 2).
# Idempotent: re-running upgrades the operator + reconciles the CR.
set -euo pipefail

NAMESPACE="${REDPANDA_NAMESPACE:-aqp-streaming}"
OPERATOR_VERSION="${REDPANDA_OPERATOR_VERSION:-25.1.5}"

helm repo add redpanda https://charts.redpanda.com >/dev/null
helm repo update redpanda >/dev/null

# Operator: cluster-scoped CRDs first (safe to apply repeatedly).
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install redpanda-operator redpanda/operator \
  --namespace "${NAMESPACE}" \
  --version "${OPERATOR_VERSION}" \
  --set crds.enabled=true \
  --wait

# Cluster CR + supporting resources (kustomize tree).
kubectl apply -k "$(dirname "$0")/../../deployments/kubernetes/base-services/redpanda/"

echo "Redpanda installed: namespace=${NAMESPACE} operator=${OPERATOR_VERSION}"
