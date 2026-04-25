<#
.SYNOPSIS
    Show AQP platform status: container health + port checks.

.DESCRIPTION
    Lists every docker compose service with its current state and probes
    the main HTTP endpoints so you can see at a glance whether the
    platform is healthy.

.EXAMPLE
    ./scripts/status.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Test-HttpEndpoint {
    param([string]$Name, [string]$Url)
    try {
        $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        Write-Host ("  OK   {0,-10} {1}" -f $Name, $Url) -ForegroundColor Green
    } catch {
        Write-Host ("  DOWN {0,-10} {1}" -f $Name, $Url) -ForegroundColor Red
    }
}

Push-Location $repoRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "docker is not installed or not on PATH."
    }

    Write-Host "Containers" -ForegroundColor Cyan
    & docker compose ps

    Write-Host ""
    Write-Host "Endpoints" -ForegroundColor Cyan
    Test-HttpEndpoint -Name "UI"     -Url "http://localhost:8765"
    Test-HttpEndpoint -Name "API"    -Url "http://localhost:8000/docs"
    Test-HttpEndpoint -Name "Dash"   -Url "http://localhost:8000/dash/"
    Test-HttpEndpoint -Name "Jaeger" -Url "http://localhost:16686"
    Test-HttpEndpoint -Name "MLflow" -Url "http://localhost:5000"
    Test-HttpEndpoint -Name "Chroma" -Url "http://localhost:8001/api/v1/heartbeat"
}
finally {
    Pop-Location
}
