#!/usr/bin/env bash
# =============================================================================
# Install / reconcile the Alpha Vantage integration (AQP-owned)
# =============================================================================
# Creates alphavantage-credentials secrets, applies AV Kafka topics (via the
# shared Strimzi topics bundle), Argo WorkflowTemplates, and the streaming
# producer Deployment (replicas=0 by default).
#
# Usage:
#   TOKEN_FILE=/path/to/token.txt bash aqp_platform/scripts/cluster_install/install-alphavantage.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
K8S_ROOT="${REPO_ROOT}/deployments/kubernetes"
TOKEN_FILE="${TOKEN_FILE:-$HOME/.alphavantage/api_key}"
WIN_DEFAULT="C:\\Users\\Julian Wiley\\Documents\\alphavantage_api_token.txt"

if [[ ! -f "$TOKEN_FILE" && -f "$WIN_DEFAULT" ]]; then
    TOKEN_FILE="$WIN_DEFAULT"
fi

if [[ ! -f "$TOKEN_FILE" ]]; then
    echo "AV token file not found at $TOKEN_FILE" >&2
    echo "Claim a free key at https://www.alphavantage.co/support/#api-key" >&2
    exit 1
fi

TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
if [[ -z "$TOKEN" ]]; then
    echo "Token file $TOKEN_FILE is empty" >&2
    exit 1
fi

upsert_secret() {
    local ns="$1"
    echo "==> Ensuring namespace $ns"
    kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f -
    echo "==> Creating/updating alphavantage-credentials in $ns"
    kubectl create secret generic alphavantage-credentials \
        --from-literal=api-key="$TOKEN" \
        --namespace="$ns" \
        --dry-run=client -o yaml | kubectl apply -f -
}

upsert_secret "aqp-streaming"
upsert_secret "aqp-mlops"

echo "==> Applying Kafka topics (includes alphavantage.*.v1)"
kubectl apply -f "${K8S_ROOT}/base-services/kafka-strimzi/topics.yaml"

echo "==> Applying Alpha Vantage Argo WorkflowTemplates + CronWorkflows"
kubectl apply -k "${K8S_ROOT}/mlops/pipelines/alphavantage/"

echo "==> Applying Alpha Vantage streaming producer (replicas=0 by default)"
kubectl apply -k "${REPO_ROOT}/templates/alphavantage-producer/kubernetes/"

if command -v curl >/dev/null 2>&1; then
    response="$(curl -sS --max-time 15 "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey=$TOKEN" || true)"
    if [[ "$response" == *"Global Quote"* ]]; then
        echo "    -> GLOBAL_QUOTE IBM succeeded"
    else
        echo "    !! AV response (may indicate throttling or bad key):"
        echo "$response" | head -c 400
    fi
fi

cat <<EOF

Alpha Vantage integration installed.
  - Secrets:           aqp-streaming/alphavantage-credentials, aqp-mlops/alphavantage-credentials
  - Kafka topics:      alphavantage.*.v1 (in kafka-strimzi/topics.yaml)
  - WorkflowTemplates: aqp_platform/deployments/kubernetes/mlops/pipelines/alphavantage/
  - Producer:          aqp-streaming/alphavantage-producer (replicas=0 default)

Enable streaming with:
    kubectl -n aqp-streaming scale deployment/alphavantage-producer --replicas=1
EOF
