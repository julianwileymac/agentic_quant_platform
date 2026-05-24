# =============================================================================
# Install / reconcile the Alpha Vantage integration (PowerShell)
# =============================================================================
# Loads the AV API token from a local file (defaults to
#   C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt
# ), creates the `alphavantage-credentials` Secret in both `data-services`
# (for the streaming producer) and `mlops` (for Argo workflows), and applies
# the dedicated Kafka topics + Argo WorkflowTemplates + streaming producer
# manifests. Safe to re-run: every step is `apply`-based.
#
# Usage:
#   pwsh bootstrap/scripts/install-alphavantage.ps1 [-TokenFile <path>]
# =============================================================================

param(
    [string]$TokenFile = "C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir "..\..")
$KafkaDir  = Join-Path $RepoRoot "kubernetes\base-services\kafka"
$MlopsAvDir = Join-Path $RepoRoot "kubernetes\mlops\pipelines\alphavantage"
$ProducerDir = Join-Path $RepoRoot "templates\alphavantage-producer\kubernetes"

if (-not (Test-Path $TokenFile)) {
    throw "AV token file not found at $TokenFile. Obtain a key at https://www.alphavantage.co/support/#api-key and save it there, or pass -TokenFile."
}

$Token = (Get-Content $TokenFile -Raw).Trim()
if (-not $Token) {
    throw "AV token file $TokenFile is empty"
}

function Upsert-Secret {
    param([string]$Namespace)
    Write-Host "==> Ensuring namespace $Namespace exists"
    kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f -
    if ($LASTEXITCODE -ne 0) { throw "failed to ensure namespace $Namespace" }

    Write-Host "==> Creating / updating Secret alphavantage-credentials in $Namespace"
    $manifest = kubectl create secret generic alphavantage-credentials `
        --from-literal=api-key="$Token" `
        --namespace=$Namespace `
        --dry-run=client -o yaml
    if ($LASTEXITCODE -ne 0) { throw "kubectl create secret failed for $Namespace" }
    $manifest | kubectl apply -f -
    if ($LASTEXITCODE -ne 0) { throw "kubectl apply secret failed for $Namespace" }
}

Upsert-Secret -Namespace "data-services"
Upsert-Secret -Namespace "mlops"

Write-Host "==> Applying Kafka topics (alphavantage.*.v1)"
kubectl apply -k $KafkaDir
if ($LASTEXITCODE -ne 0) { throw "kafka kustomization apply failed" }

Write-Host "==> Applying Alpha Vantage Argo WorkflowTemplates + CronWorkflows"
kubectl apply -k $MlopsAvDir
if ($LASTEXITCODE -ne 0) { throw "alphavantage kustomization apply failed" }

Write-Host "==> Applying Alpha Vantage producer Deployment (replicas=0 by default)"
kubectl apply -k $ProducerDir
if ($LASTEXITCODE -ne 0) { throw "producer kustomization apply failed" }

Write-Host ""
Write-Host "==> Smoke test: live API call via curl"
try {
    $resp = Invoke-RestMethod -Uri "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey=$Token" -TimeoutSec 15
    if ($resp.'Global Quote') {
        Write-Host "    -> GLOBAL_QUOTE IBM price=$($resp.'Global Quote'.'05. price')"
    } elseif ($resp.Note -or $resp.Information) {
        Write-Warning "AV responded with a throttle notice: $(($resp.Note, $resp.Information | Where-Object { $_ }) -join ' / ')"
    } else {
        Write-Warning "Unexpected AV response: $($resp | ConvertTo-Json -Depth 3)"
    }
} catch {
    Write-Warning "Smoke test request failed: $_"
}

Write-Host ""
Write-Host "Alpha Vantage integration installed."
Write-Host "  - Secret:           data-services/alphavantage-credentials, mlops/alphavantage-credentials"
Write-Host "  - Kafka topics:     alphavantage.*.v1 (see kafka-resources.md)"
Write-Host "  - WorkflowTemplates: av-bulk, av-bulk-timeseries, av-intraday-backfill, av-fundamentals,"
Write-Host "                       av-universe-sync, av-news-ingest, av-fx-backfill, av-crypto-backfill,"
Write-Host "                       av-technicals, av-commodities, av-economics, av-earnings"
Write-Host "  - CronWorkflows:    av-universe-sync-hourly, av-daily-refresh"
Write-Host "  - Producer:         deployment/alphavantage-producer in data-services (replicas=0 by default)"
Write-Host ""
Write-Host "Enable the streaming producer with:"
Write-Host "    kubectl -n aqp-data-services scale deployment/alphavantage-producer --replicas=1"
Write-Host "Or via the management UI at /alphavantage/admin."
