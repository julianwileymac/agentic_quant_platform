#!/usr/bin/env bash
# install-kube-prometheus-stack.sh — Prometheus + Grafana + Alertmanager
# Helm release into the aqp-observability namespace. Phase 2c of the
# AQP infra-expansion plan.
set -euo pipefail

NAMESPACE="${KUBE_PROM_NAMESPACE:-aqp-observability}"
CHART_VERSION="${KUBE_PROM_VERSION:-72.0.0}"
VALUES_PATH="$(dirname "$0")/../../deployments/kubernetes/observability/kube-prometheus-stack/helm-values.yaml"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update prometheus-community >/dev/null

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# helm-values.yaml is shipped as a ConfigMap; extract the values.yaml key
# into a temp file for `helm upgrade`.
TMP_VALUES="$(mktemp)"
trap 'rm -f "${TMP_VALUES}"' EXIT
kubectl get configmap kube-prometheus-stack-values -n "${NAMESPACE}" -o jsonpath='{.data.values\.yaml}' >"${TMP_VALUES}" || \
  python3 -c "import yaml,sys; cm=yaml.safe_load(open(sys.argv[1])); print(cm['data']['values.yaml'])" "${VALUES_PATH}" >"${TMP_VALUES}"

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace "${NAMESPACE}" \
  --version "${CHART_VERSION}" \
  --values "${TMP_VALUES}" \
  --wait

# Apply the AQP-side ServiceMonitor / PrometheusRule + Grafana datasource ConfigMap.
kubectl apply -k "$(dirname "$0")/../../deployments/kubernetes/observability/kube-prometheus-stack/"

echo "kube-prometheus-stack installed: namespace=${NAMESPACE} chart=${CHART_VERSION}"
