#!/usr/bin/env bash
set -euo pipefail

# verify_blue_green_cutover.sh
# Validate green-lane ingress + cloudflared artifacts before DNS/tunnel switch.

GREEN_FRONTEND_HOST="${GREEN_FRONTEND_HOST:-aqp-green.aqp.fund}"
GREEN_API_HOST="${GREEN_API_HOST:-api-green.aqp.fund}"
GREEN_MANAGE_HOST="${GREEN_MANAGE_HOST:-manage-green.aqp.fund}"
CHECK_EXTERNAL="${CHECK_EXTERNAL:-false}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required." >&2
  exit 1
fi

echo "[verify] ingress hosts for green lane"
kubectl -n aqp get ingress aqp-client aqp-core
kubectl -n aqp-admin get ingress aqp-cp

CLIENT_HOST="$(kubectl -n aqp get ingress aqp-client -o jsonpath='{.spec.rules[0].host}')"
API_HOST="$(kubectl -n aqp get ingress aqp-core -o jsonpath='{.spec.rules[0].host}')"
MANAGE_HOST="$(kubectl -n aqp-admin get ingress aqp-cp -o jsonpath='{.spec.rules[0].host}')"

[[ "${CLIENT_HOST}" == "${GREEN_FRONTEND_HOST}" ]] || { echo "unexpected client host: ${CLIENT_HOST}" >&2; exit 1; }
[[ "${API_HOST}" == "${GREEN_API_HOST}" ]] || { echo "unexpected api host: ${API_HOST}" >&2; exit 1; }
[[ "${MANAGE_HOST}" == "${GREEN_MANAGE_HOST}" ]] || { echo "unexpected manage host: ${MANAGE_HOST}" >&2; exit 1; }

echo "[verify] green lane configmaps"
kubectl -n aqp get configmap aqp-config -o jsonpath='{.data.AQP_INGRESS_BASE_URL}' | grep -q "${GREEN_FRONTEND_HOST}"
kubectl -n aqp-admin get configmap aqp-config -o jsonpath='{.data.AQP_INGRESS_BASE_URL}' | grep -q "${GREEN_MANAGE_HOST}"

echo "[verify] cloudflared green deployment"
kubectl -n aqp-edge rollout status deploy/cloudflared-aqp-green --timeout="${VERIFY_TIMEOUT_SECONDS:-180}s"
kubectl -n aqp-edge get svc cloudflared-aqp-green-metrics >/dev/null

if [[ "${CHECK_EXTERNAL}" == "true" ]]; then
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required when CHECK_EXTERNAL=true" >&2
    exit 1
  fi
  echo "[verify] external host probes"
  curl -fsS "https://${GREEN_FRONTEND_HOST}" >/dev/null
  curl -fsS "https://${GREEN_API_HOST}/livez" >/dev/null
  curl -fsS "https://${GREEN_MANAGE_HOST}/manage/livez" >/dev/null
fi

echo "[verify] green lane checks passed."
echo "[rollback] kubectl apply -k aqp_platform/deployments/kubernetes/overlays/tower-dev/"
echo "[rollback] kubectl delete -k aqp_platform/deployments/kubernetes/edge/cloudflared-aqp-green/"
