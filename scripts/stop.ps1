<#
.SYNOPSIS
    Stop the Agentic Quant Platform stack.

.DESCRIPTION
    Runs ``docker compose down`` to tear down all AQP containers.  Data
    volumes (redis, postgres, mlflow) are preserved by default so the
    next ``start.ps1`` keeps your state.

.PARAMETER Volumes
    If present, also deletes named volumes (DESTROYS DATA). Equivalent
    to ``docker compose down --volumes``.

.PARAMETER Orphans
    If present, removes services defined in profiles you aren't using.
    Equivalent to ``docker compose down --remove-orphans``.

.EXAMPLE
    ./scripts/stop.ps1

.EXAMPLE
    ./scripts/stop.ps1 -Volumes   # full reset
#>
[CmdletBinding()]
param(
    [switch]$Volumes,
    [switch]$Orphans
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "docker is not installed or not on PATH."
    }

    $args = @("compose", "down")
    if ($Volumes) {
        Write-Warning "Deleting data volumes (redis, postgres, mlflow)..."
        $args += "--volumes"
    }
    if ($Orphans) {
        $args += "--remove-orphans"
    }

    Write-Host "Stopping AQP stack..." -ForegroundColor Cyan
    & docker @args
    if ($LASTEXITCODE -ne 0) {
        Write-Error "docker compose down failed (exit $LASTEXITCODE)"
    }

    Write-Host "AQP stopped." -ForegroundColor Green
}
finally {
    Pop-Location
}
