#!/usr/bin/env bash
# Regenerate the typed OpenAPI client used by webui/.
#
#   1. Dump the live FastAPI spec to data/openapi.json
#   2. Run openapi-typescript to emit webui/lib/api/generated/schema.d.ts
#
# Requires: a working Python environment (the aqp package importable) and
# pnpm available on PATH.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[gen_webui_client] dumping OpenAPI spec ..."
python -m scripts.export_openapi --out data/openapi.json

echo "[gen_webui_client] regenerating webui TypeScript types ..."
pnpm --dir webui exec openapi-typescript ../data/openapi.json -o lib/api/generated/schema.d.ts

echo "[gen_webui_client] done."
