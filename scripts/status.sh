#!/usr/bin/env bash
# Show AQP platform status: container health + port checks.
#
# Usage:
#   ./scripts/status.sh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

probe() {
    local name="$1" url="$2"
    if curl -sf -o /dev/null --max-time 2 "$url"; then
        printf "  OK   %-10s %s\n" "$name" "$url"
    else
        printf "  DOWN %-10s %s\n" "$name" "$url"
    fi
}

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is not installed or not on PATH" >&2
    exit 1
fi

echo "Containers"
docker compose ps

echo
echo "Endpoints"
probe "UI"     "http://localhost:8765"
probe "API"    "http://localhost:8000/docs"
probe "Dash"   "http://localhost:8000/dash/"
probe "Jaeger" "http://localhost:16686"
probe "MLflow" "http://localhost:5000"
probe "Chroma" "http://localhost:8001/api/v1/heartbeat"
