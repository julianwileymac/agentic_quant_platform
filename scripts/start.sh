#!/usr/bin/env bash
# Start the Agentic Quant Platform stack via Terraform + k3d.
#
# Delegates to ``aqp deploy up`` so each apply lands a row in
# terraform_runs (rule 42), emits canonical progress frames, and is
# halt-able from the global KillSwitch.
#
# Usage:
#   ./scripts/start.sh                 # default: 'aqp deploy up'
#   ./scripts/start.sh --build         # 'aqp deploy build' first, then up
#   ./scripts/start.sh --legacy        # bypass: docker compose up -d
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

BUILD=0
LEGACY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build)
            BUILD=1; shift;;
        --legacy)
            LEGACY=1; shift;;
        -h|--help)
            sed -n '2,12p' "$0"; exit 0;;
        *)
            echo "unknown arg: $1" >&2; exit 2;;
    esac
done

if [[ "$LEGACY" -eq 1 ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "error: docker not on PATH" >&2; exit 1
    fi
    echo "[start.sh] Legacy mode — bringing up docker compose stack..."
    docker compose up -d
    exit $?
fi

if ! command -v aqp >/dev/null 2>&1; then
    echo "error: 'aqp' CLI not on PATH. Install with 'pip install -e .' or use --legacy." >&2
    exit 1
fi

if [[ "$BUILD" -eq 1 ]]; then
    echo "[start.sh] aqp deploy build (rebuild + push images)"
    aqp deploy build
fi

echo "[start.sh] aqp deploy up (Terraform + k3d)"
aqp deploy up

cat <<EOF

AQP is up.

  Next:
    ./scripts/status.sh     # pod / service rollup
    aqp deploy endpoints    # printable URL list
    aqp deploy logs api     # tail API pod logs

Stop with: ./scripts/stop.sh
EOF
