# =============================================================================
# Install / Reconcile Redis 8 Stack (PowerShell port of install-redis.sh)
# =============================================================================
# Applies kubernetes/base-services/redis/, waits for the Deployment to roll
# out, then runs a smoke test (PING + MODULE LIST + FT._LIST) so failures
# surface immediately instead of after the next consumer tries to connect.
#
# Usage:
#   pwsh bootstrap/scripts/install-redis.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir "..\..")
$KustomizeDir = Join-Path $RepoRoot "kubernetes\base-services\redis"
$Namespace = "data-services"

Write-Host "==> Applying Redis Stack manifests from $KustomizeDir"
kubectl apply -k $KustomizeDir
if ($LASTEXITCODE -ne 0) { throw "kubectl apply failed" }

Write-Host "==> Waiting for redis Deployment to become Ready (timeout 5m)"
kubectl -n $Namespace rollout status deployment/redis --timeout=5m
if ($LASTEXITCODE -ne 0) { throw "redis rollout did not complete" }

Write-Host "==> Waiting for redis-exporter Deployment to become Ready (timeout 2m)"
kubectl -n $Namespace rollout status deployment/redis-exporter --timeout=2m
if ($LASTEXITCODE -ne 0) { throw "redis-exporter rollout did not complete" }

# Pull the password from the Secret so smoke tests can authenticate.
$PasswordB64 = kubectl -n $Namespace get secret redis-credentials -o jsonpath='{.data.password}'
$Password    = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($PasswordB64))

Write-Host "==> Smoke test: PING"
$Pong = kubectl -n $Namespace exec deploy/redis -- redis-cli -a $Password --no-auth-warning ping
if ($Pong -notmatch "PONG") {
    throw "Redis PING returned '$Pong' instead of 'PONG'"
}
Write-Host "    -> PING OK"

Write-Host "==> Smoke test: MODULE LIST"
$ModulesRaw = kubectl -n $Namespace exec deploy/redis -- redis-cli -a $Password --no-auth-warning MODULE LIST
Write-Host $ModulesRaw
foreach ($required in @("search", "ReJSON", "timeseries", "bf")) {
    if ($ModulesRaw -notmatch [regex]::Escape($required)) {
        throw "Required Redis module '$required' not loaded"
    }
}
Write-Host "    -> All required modules present (search, ReJSON, timeseries, bf)"

Write-Host "==> Smoke test: FT._LIST"
$FtList = kubectl -n $Namespace exec deploy/redis -- redis-cli -a $Password --no-auth-warning FT._LIST
Write-Host "    indexes: $FtList"

Write-Host "==> Smoke test: redis_exporter /metrics"
$ExporterPod = kubectl -n $Namespace get pod -l app=redis-exporter -o jsonpath='{.items[0].metadata.name}'
$Metrics = kubectl -n $Namespace exec $ExporterPod -- wget -qO- http://localhost:9121/metrics | Select-Object -First 5
if (-not $Metrics) {
    throw "redis-exporter /metrics endpoint did not respond"
}
Write-Host "    -> exporter OK"

Write-Host "==> Done. Redis 8 Stack is ready."
Write-Host "    Service:        redis.$Namespace.svc.cluster.local:6379"
Write-Host "    RAGFlow alias:  ragflow-redis.$Namespace.svc.cluster.local:6379"
Write-Host "    Exporter:       redis-exporter.$Namespace.svc.cluster.local:9121"
Write-Host "    Password secret: $Namespace/redis-credentials (key=password)"
