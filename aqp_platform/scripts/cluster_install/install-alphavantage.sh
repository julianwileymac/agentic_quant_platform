#!/usr/bin/env bash
# =============================================================================
# Install / reconcile the Alpha Vantage integration
# =============================================================================
# Loads the AV API token from a local file (default: the Windows path
#   "$HOME/.alphavantage/api_key" on Unix, or the TOKEN_FILE env override),
# creates the `alphavantage-credentials` Secret in both `data-services`
# (for the streaming producer) and `mlops` (for Argo workflows), and applies
# the dedicated Kafka topics + Argo WorkflowTemplates + streaming producer
# manifests. Safe to re-run: every step is `apply`-based.
#
# Usage:
#   TOKEN_FILE=/path/to/token.txt bootstrap/scripts/install-alphavantage.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TOKEN_FILE="${TOKEN_FILE:-$HOME/.alphavantage/api_key}"
WIN_DEFAULT="C:\\Users\\Julian Wiley\\Documents\\alphavantage_api_token.txt"

if [[ ! -f "$TOKEN_FILE" && -f "$WIN_DEFAULT" ]]; then
    TOKEN_FILE="$WIN_DEFAULT"
fi

if [[ ! -f "$TOKEN_FILE" ]]; then
    echo "AV token file not found at $TOKEN_FILE" >&2
    echo "Claim a free key at https://www.alphavantage.co/support/#api-key and save it there," >&2
    echo "or rerun with TOKEN_FILE=/path/to/token.txt bootstrap/scripts/install-alphavantage.sh" >&2
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

    echo "==> Creating/updating alphavantage-credentials Secret in $ns"
    kubectl create secret generic alphavantage-credentials \
        --from-literal=api-key="$TOKEN" \
        --namespace="$ns" \
        --dry-run=client -o yaml | kubectl apply -f -
}

upsert_secret "data-services"
upsert_secret "mlops"

echo "==> Applying Kafka topics (alphavantage.*.v1)"
kubectl apply -k "$REPO_ROOT/kubernetes/base-services/kafka"

echo "==> Applying Alpha Vantage Argo WorkflowTemplates + CronWorkflows"
kubectl apply -k "$REPO_ROOT/kubernetes/mlops/pipelines/alphavantage"

echo "==> Applying Alpha Vantage streaming producer (replicas=0 by default)"
kubectl apply -k "$REPO_ROOT/templates/alphavantage-producer/kubernetes"

echo "==> Smoke test: live API call"
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
  - Secret:            data-services/alphavantage-credentials, mlops/alphavantage-credentials
  - Kafka topics:      alphavantage.*.v1 (see aqp_docs/kafka-resources.md)
  - WorkflowTemplates: av-bulk, av-bulk-timeseries, av-intraday-backfill, av-fundamentals,
                       av-universe-sync, av-news-ingest, av-fx-backfill, av-crypto-backfill,
                       av-technicals, av-commodities, av-economics, av-earnings
  - CronWorkflows:     av-universe-sync-hourly, av-daily-refresh
  - Producer:          deployment/alphavantage-producer (data-services), replicas=0 default

Enable streaming with:
    kubectl -n aqp-data-services scale deployment/alphavantage-producer --replicas=1
Or via the management UI at /alphavantage/admin.
EOF
