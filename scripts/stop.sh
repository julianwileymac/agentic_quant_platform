#!/usr/bin/env bash
# Tear down the Agentic Quant Platform stack via Terraform.
#
# Usage:
#   ./scripts/stop.sh                 # confirm prompt + destroy
#   ./scripts/stop.sh --yes           # skip confirmation
#   ./scripts/stop.sh --legacy        # bypass: docker compose down
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

YES=0
LEGACY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y) YES=1; shift;;
        --legacy) LEGACY=1; shift;;
        -h|--help) sed -n '2,8p' "$0"; exit 0;;
        *) echo "unknown arg: $1" >&2; exit 2;;
    esac
done

if [[ "$LEGACY" -eq 1 ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "error: docker not on PATH" >&2; exit 1
    fi
    echo "[stop.sh] Legacy mode — docker compose down"
    docker compose down
    exit $?
fi

if ! command -v aqp >/dev/null 2>&1; then
    echo "error: 'aqp' CLI not on PATH. Use --legacy or 'pip install -e .'." >&2
    exit 1
fi

echo "[stop.sh] aqp deploy down (Terraform destroy)"
if [[ "$YES" -eq 1 ]]; then
    aqp deploy down --yes
else
    aqp deploy down
fi
echo "AQP stopped."
