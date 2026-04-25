<#
.SYNOPSIS
    Start the Agentic Quant Platform stack.

.DESCRIPTION
    Brings up the docker compose services (redis, postgres, mlflow, chromadb,
    otel-collector, jaeger, api, worker(s), ui, paper-trader, beat).  Waits
    for health checks and prints the primary endpoints once the platform
    is reachable.

.PARAMETER Profile
    Optional docker compose profile to enable (e.g. "streaming" for the
    Kafka + IB Gateway pipeline).

.PARAMETER Pull
    If present, pulls the latest images before starting.

.PARAMETER Build
    If present, rebuilds the api / worker / ui images before starting.

.EXAMPLE
    ./scripts/start.ps1

.EXAMPLE
    ./scripts/start.ps1 -Pull -Build

.EXAMPLE
    ./scripts/start.ps1 -Profile streaming
#>
[CmdletBinding()]
param(
    [string]$Profile = "",
    [switch]$Pull,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "docker is not installed or not on PATH. Install Docker Desktop first."
    }

    $composeArgs = @()
    if ($Profile) {
        $composeArgs += @("--profile", $Profile)
    }

    if ($Pull) {
        Write-Host "Pulling latest images..." -ForegroundColor Cyan
        & docker compose @composeArgs pull
    }

    if ($Build) {
        Write-Host "Rebuilding local images..." -ForegroundColor Cyan
        & docker compose @composeArgs build
    }

    Write-Host "Starting AQP stack..." -ForegroundColor Cyan
    & docker compose @composeArgs up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Error "docker compose up failed (exit $LASTEXITCODE)"
    }

    Write-Host ""
    Write-Host "Waiting for API health..." -ForegroundColor Cyan
    $apiReady = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:8000/" -UseBasicParsing -TimeoutSec 2
            $apiReady = $true
            break
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $apiReady) {
        Write-Warning "API did not respond within 60s; check 'scripts/status.ps1'"
    }

    Write-Host ""
    Write-Host "AQP is up." -ForegroundColor Green
    Write-Host ""
    Write-Host "  UI          http://localhost:8765"
    Write-Host "  API docs    http://localhost:8000/docs"
    Write-Host "  Dash        http://localhost:8000/dash/"
    Write-Host "  Jaeger      http://localhost:16686"
    Write-Host "  MLflow      http://localhost:5000"
    Write-Host ""
    Write-Host "Stop with: ./scripts/stop.ps1" -ForegroundColor DarkGray
}
finally {
    Pop-Location
}
