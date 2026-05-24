#Requires -Version 5.1
# =============================================================================
# Install or upgrade Grafana Loki (MinIO S3 backend) in observability namespace
# =============================================================================
param(
    [string]$Namespace = "observability",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
$Values = Join-Path $RepoRoot "kubernetes\observability\loki\values.yaml"

Write-Host "==> Ensuring Grafana Helm repo"
helm repo add grafana https://grafana.github.io/helm-charts 2>$null
helm repo update grafana

Write-Host "==> Creating MinIO buckets for Loki (data-services)"
$mc = 'mc alias set local http://127.0.0.1:9000 minioadmin minioadmin123 && mc mb local/loki-chunks --ignore-existing && mc mb local/loki-ruler --ignore-existing'
kubectl exec -n aqp-data-services deploy/minio -- sh -c $mc

Write-Host "==> Installing / upgrading Loki"
helm upgrade --install loki grafana/loki `
  --namespace $Namespace `
  --create-namespace `
  -f $Values

Write-Host "==> Done. Loki query API: http://loki.${Namespace}:3100 (in-cluster)"
