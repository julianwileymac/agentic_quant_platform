<#
.SYNOPSIS
    Tear down the Agentic Quant Platform stack via Terraform.

.DESCRIPTION
    Delegates to ``aqp deploy down`` which routes through TerraformRuntime
    so the destroy lands a row in ``terraform_runs`` (rule 42) and is
    halt-able from the global KillSwitch.

    Image registry + cluster volumes are removed by Terraform's destroy
    of the ``module.local_cluster.null_resource.cluster`` resource —
    there's no Volumes flag because destroy is total.

.PARAMETER Yes
    Skip the confirmation prompt.

.PARAMETER Legacy
    Bypass Terraform; tear down docker-compose directly.

.EXAMPLE
    ./scripts/stop.ps1
    ./scripts/stop.ps1 -Yes
    ./scripts/stop.ps1 -Legacy
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$Legacy
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    if ($Legacy) {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Write-Error "docker is not installed or not on PATH."
        }
        Write-Host "[stop.ps1] Legacy mode — docker compose down" -ForegroundColor Yellow
        & docker compose down
        return
    }

    if (-not (Get-Command aqp -ErrorAction SilentlyContinue)) {
        Write-Error "'aqp' CLI not on PATH. Use -Legacy or 'pip install -e .'."
    }

    Write-Host "[stop.ps1] aqp deploy down (Terraform destroy)" -ForegroundColor Cyan
    if ($Yes) {
        & aqp deploy down --yes
    } else {
        & aqp deploy down
    }
    if ($LASTEXITCODE -ne 0) { Write-Error "aqp deploy down failed (exit $LASTEXITCODE)" }
    Write-Host "AQP stopped." -ForegroundColor Green
}
finally {
    Pop-Location
}
