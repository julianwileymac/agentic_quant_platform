#!/usr/bin/env bash
# Run Alembic against the cluster Postgres (brownfield-safe).
#
# Prerequisites:
#   - kubectl context pointing at the rpi cluster
#   - Local image: agentic_quant_platform-api:latest (or set AQP_MIGRATE_IMAGE)
#   - Port-forward: kubectl -n data-services port-forward svc/postgresql 15432:5432
#
# Brownfield databases that pre-date Alembic tracking may need an explicit stamp
# before ``upgrade head``. Inspect tables, pick the highest revision whose schema
# is already present, then:
#   export AQP_ALEMBIC_STAMP_REVISION=0015_dbt_foundation
#   ./scripts/cluster_alembic_upgrade.sh
#
set -euo pipefail

IMAGE="${AQP_MIGRATE_IMAGE:-agentic_quant_platform-api:latest}"
DSN="${AQP_POSTGRES_DSN:-postgresql+psycopg2://aqp:aqp@host.docker.internal:15432/aqp}"
STAMP="${AQP_ALEMBIC_STAMP_REVISION:-}"

if [[ -n "${STAMP}" ]]; then
  echo "Stamping alembic to ${STAMP} ..."
  docker run --rm -e "AQP_POSTGRES_DSN=${DSN}" "${IMAGE}" \
    alembic stamp "${STAMP}"
fi

echo "Running alembic upgrade head ..."
docker run --rm -e "AQP_POSTGRES_DSN=${DSN}" "${IMAGE}" alembic upgrade head
docker run --rm -e "AQP_POSTGRES_DSN=${DSN}" "${IMAGE}" alembic current
