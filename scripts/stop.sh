#!/usr/bin/env bash
# Stop the Agentic Quant Platform stack.
#
# Usage:
#   ./scripts/stop.sh                  # stop all containers, keep data
#   ./scripts/stop.sh --volumes        # also delete named volumes (DESTROYS DATA)
#   ./scripts/stop.sh --orphans        # remove services from inactive profiles
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

VOLUMES=0
ORPHANS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --volumes) VOLUMES=1; shift;;
        --orphans) ORPHANS=1; shift;;
        -h|--help) sed -n '2,7p' "$0"; exit 0;;
        *) echo "unknown arg: $1" >&2; exit 2;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is not installed or not on PATH" >&2
    exit 1
fi

ARGS=(compose down)
if [[ "$VOLUMES" -eq 1 ]]; then
    echo "warning: deleting data volumes (redis, postgres, mlflow)..." >&2
    ARGS+=(--volumes)
fi
if [[ "$ORPHANS" -eq 1 ]]; then
    ARGS+=(--remove-orphans)
fi

echo "Stopping AQP stack..."
docker "${ARGS[@]}"
echo "AQP stopped."
