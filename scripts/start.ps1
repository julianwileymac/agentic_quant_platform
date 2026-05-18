<#
.SYNOPSIS
    Start the Agentic Quant Platform stack via Terraform + k3d.

.DESCRIPTION
    Delegates to ``aqp deploy up`` — the new canonical entrypoint that
    routes through TerraformRuntime so each apply lands a row in
    ``terraform_runs`` (rule 42), emits canonical progress frames, and
    is halt-able from the global KillSwitch.

    The legacy docker-compose path is still available via
    ``./scripts/start.ps1 -Legacy`` (which runs ``make up-compose-legacy``).

.PARAMETER Build
    If present, runs ``aqp deploy build`` first to rebuild + push every
    AQP image into the local k3d registry.

.PARAMETER Legacy
    Bypass Terraform; bring up the docker-compose stack directly. Use
    only when k3d / Terraform is broken locally.

.EXAMPLE
    ./scripts/start.ps1

.EXAMPLE
    ./scripts/start.ps1 -Build

.EXAMPLE
    ./scripts/start.ps1 -Legacy
#>
[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$Legacy
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    if ($Legacy) {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Write-Error "docker is not installed or not on PATH. Install Docker Desktop first."
        }
        Write-Host "[start.ps1] Legacy mode — bringing up docker compose stack..." -ForegroundColor Yellow
        & docker compose up -d
        if ($LASTEXITCODE -ne 0) { Write-Error "docker compose up failed" }
        return
    }

    if (-not (Get-Command aqp -ErrorAction SilentlyContinue)) {
        Write-Error "'aqp' CLI not on PATH. Install with 'pip install -e .' from the repo root, or use -Legacy."
    }

    if ($Build) {
        Write-Host "[start.ps1] aqp deploy build (rebuild + push images)" -ForegroundColor Cyan
        & aqp deploy build
        if ($LASTEXITCODE -ne 0) { Write-Error "aqp deploy build failed (exit $LASTEXITCODE)" }
    }

    Write-Host "[start.ps1] aqp deploy up (Terraform + k3d)" -ForegroundColor Cyan
    & aqp deploy up
    if ($LASTEXITCODE -ne 0) { Write-Error "aqp deploy up failed (exit $LASTEXITCODE)" }

    Write-Host ""
    Write-Host "AQP is up." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Next:"
    Write-Host "    ./scripts/status.ps1     # pod / service rollup"
    Write-Host "    aqp deploy endpoints     # printable URL list"
    Write-Host "    aqp deploy logs api      # tail API pod logs"
    Write-Host ""
    Write-Host "Stop with: ./scripts/stop.ps1" -ForegroundColor DarkGray
}
finally {
    Pop-Location
}
