<#
.SYNOPSIS
    Show AQP local stack status: pod / service rollup + endpoint probes.

.DESCRIPTION
    Delegates to ``aqp deploy status`` which calls ``kubectl get pods``
    and ``kubectl get svc`` for the aqp-local namespace, then prints
    the Terraform-published endpoint URLs.

.PARAMETER Legacy
    Show docker-compose status instead.

.EXAMPLE
    ./scripts/status.ps1
    ./scripts/status.ps1 -Legacy
#>
[CmdletBinding()]
param(
    [switch]$Legacy
)

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
    if ($Legacy) {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Write-Error "docker is not installed or not on PATH."
        }
        Write-Host "Containers (legacy)" -ForegroundColor Cyan
        & docker compose ps
        Write-Host ""
        Write-Host "Endpoints (legacy)" -ForegroundColor Cyan
        Test-HttpEndpoint -Name "API"    -Url "http://localhost:8000/docs"
        Test-HttpEndpoint -Name "Jaeger" -Url "http://localhost:16686"
        Test-HttpEndpoint -Name "MLflow" -Url "http://localhost:5000"
        return
    }

    if (-not (Get-Command aqp -ErrorAction SilentlyContinue)) {
        Write-Error "'aqp' CLI not on PATH. Use -Legacy or install with 'pip install -e .'."
    }

    Write-Host "Pods + services" -ForegroundColor Cyan
    & aqp deploy status

    Write-Host ""
    Write-Host "HTTP probes (Traefik on :8000)" -ForegroundColor Cyan
    Test-HttpEndpoint -Name "Frontend" -Url "http://localhost:8000/"
    Test-HttpEndpoint -Name "API"      -Url "http://localhost:8000/api/healthz"
}
finally {
    Pop-Location
}
