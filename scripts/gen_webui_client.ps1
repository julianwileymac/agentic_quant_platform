# Regenerate the typed OpenAPI client used by webui/.
#   1. Dump the live FastAPI spec to data/openapi.json
#   2. Run openapi-typescript to emit webui/lib/api/generated/schema.d.ts
#
# Usage (from any directory):
#   pwsh ./scripts/gen_webui_client.ps1

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot

try {
    Write-Host "[gen_webui_client] dumping OpenAPI spec ..." -ForegroundColor Cyan
    python -m scripts.export_openapi --out data/openapi.json

    Write-Host "[gen_webui_client] regenerating webui TypeScript types ..." -ForegroundColor Cyan
    pnpm --dir webui exec openapi-typescript ../data/openapi.json -o lib/api/generated/schema.d.ts

    Write-Host "[gen_webui_client] done." -ForegroundColor Green
}
finally {
    Pop-Location
}
