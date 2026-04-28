#!/usr/bin/env bash
# AQP Dagster code-location entrypoint.
#
# Defaults are overridable via env vars to match the rpi_kubernetes
# values-pipelines-user-code.yaml conventions:
#
#   AQP_DAGSTER_GRPC_HOST=0.0.0.0
#   AQP_DAGSTER_GRPC_PORT=4000
#   AQP_DAGSTER_MODULE_PATH=aqp.dagster.definitions
#   AQP_DAGSTER_CODE_LOCATION=aqp
set -euo pipefail

HOST="${AQP_DAGSTER_GRPC_HOST:-0.0.0.0}"
PORT="${AQP_DAGSTER_GRPC_PORT:-4000}"
MODULE="${AQP_DAGSTER_MODULE_PATH:-aqp.dagster.definitions}"
LOCATION="${AQP_DAGSTER_CODE_LOCATION:-aqp}"

exec dagster api grpc \
  --host "${HOST}" \
  --port "${PORT}" \
  --module-name "${MODULE}" \
  --location-name "${LOCATION}"
