#!/usr/bin/env bash
# Start the Agentic Quant Platform stack via docker compose.
#
# Usage:
#   ./scripts/start.sh                 # default: start all services
#   ./scripts/start.sh --pull          # pull latest images first
#   ./scripts/start.sh --build         # rebuild local images first
#   ./scripts/start.sh --profile streaming   # enable the streaming profile
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

PROFILE=""
PULL=0
BUILD=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            PROFILE="$2"; shift 2;;
        --pull)
            PULL=1; shift;;
        --build)
            BUILD=1; shift;;
        -h|--help)
            sed -n '2,8p' "$0"; exit 0;;
        *)
            echo "unknown arg: $1" >&2; exit 2;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is not installed or not on PATH" >&2
    exit 1
fi

COMPOSE_ARGS=()
if [[ -n "$PROFILE" ]]; then
    COMPOSE_ARGS+=(--profile "$PROFILE")
fi

if [[ "$PULL" -eq 1 ]]; then
    echo "Pulling latest images..."
    docker compose "${COMPOSE_ARGS[@]}" pull
fi

if [[ "$BUILD" -eq 1 ]]; then
    echo "Rebuilding local images..."
    docker compose "${COMPOSE_ARGS[@]}" build
fi

echo "Starting AQP stack..."
docker compose "${COMPOSE_ARGS[@]}" up -d

echo "Waiting for API health..."
for _ in $(seq 1 30); do
    if curl -sf "http://localhost:8000/" >/dev/null 2>&1; then
        ready=1; break
    fi
    sleep 2
done
if [[ "${ready:-0}" -ne 1 ]]; then
    echo "warning: API did not respond within 60s; run scripts/status.sh"
fi

cat <<EOF

AQP is up.

  UI          http://localhost:8765
  API docs    http://localhost:8000/docs
  Dash        http://localhost:8000/dash/
  Jaeger      http://localhost:16686
  MLflow      http://localhost:5000

Stop with: ./scripts/stop.sh
EOF
