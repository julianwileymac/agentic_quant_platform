#!/usr/bin/env bash
# Show AQP local stack status: pod / service rollup + endpoint probes.
#
# Usage:
#   ./scripts/status.sh
#   ./scripts/status.sh --legacy   # docker compose status
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

LEGACY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --legacy) LEGACY=1; shift;;
        -h|--help) sed -n '2,7p' "$0"; exit 0;;
        *) echo "unknown arg: $1" >&2; exit 2;;
    esac
done

probe() {
    local name="$1" url="$2"
    if curl -sf -o /dev/null --max-time 2 "$url"; then
        printf "  OK   %-10s %s\n" "$name" "$url"
    else
        printf "  DOWN %-10s %s\n" "$name" "$url"
    fi
}

if [[ "$LEGACY" -eq 1 ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "error: docker not on PATH" >&2; exit 1
    fi
    echo "Containers (legacy)"
    docker compose ps
    echo
    echo "Endpoints (legacy)"
    probe "API"    "http://localhost:8000/docs"
    probe "Jaeger" "http://localhost:16686"
    probe "MLflow" "http://localhost:5000"
    exit 0
fi

if ! command -v aqp >/dev/null 2>&1; then
    echo "error: 'aqp' CLI not on PATH. Use --legacy or 'pip install -e .'." >&2
    exit 1
fi

echo "Pods + services"
aqp deploy status

echo
echo "HTTP probes (Traefik on :8000)"
probe "Frontend" "http://localhost:8000/"
probe "API"      "http://localhost:8000/api/healthz"
