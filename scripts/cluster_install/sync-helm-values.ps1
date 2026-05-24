# =============================================================================
# Sync Helm chart values into the in-cluster helm-runner ConfigMap.
# =============================================================================
# Why this exists:
#   The in-cluster helm-runner Jobs (kubernetes/bootstrap/helm-runner/job-*.yaml)
#   read chart values from a ConfigMap so they don't need the repo checked
#   out.  When you edit the canonical values.yaml under
#   kubernetes/mlops/dagster/, kubernetes/mlops/kserve/, or
#   kubernetes/base-services/airbyte/, run this script
#   to push the new content into the ConfigMap that the next Job run will
#   pick up.
#
# Usage:
#   .\bootstrap\scripts\sync-helm-values.ps1
#   .\bootstrap\scripts\sync-helm-values.ps1 -KubeConfig path\to\kubeconfig
# =============================================================================
[CmdletBinding()]
param(
    [string]$KubeConfig = "$PSScriptRoot\..\..\kubeconfig.yaml"
)

$ErrorActionPreference = "Stop"
$env:KUBECONFIG = (Resolve-Path $KubeConfig).Path

$repoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$dagsterValues = Join-Path $repoRoot 'kubernetes\mlops\dagster\values.yaml'
$kserveValues  = Join-Path $repoRoot 'kubernetes\mlops\kserve\values-kserve.yaml'
$airbyteValues = Join-Path $repoRoot 'kubernetes\base-services\airbyte\values.yaml'

if (-not (Test-Path $dagsterValues)) { throw "missing $dagsterValues" }
if (-not (Test-Path $kserveValues))  { throw "missing $kserveValues" }
if (-not (Test-Path $airbyteValues)) { throw "missing $airbyteValues" }

Write-Host "==> Syncing helm-runner-values ConfigMap from canonical chart values"
kubectl create configmap helm-runner-values `
    --namespace helm-runner `
    --from-file=values-kserve.yaml=$kserveValues `
    --from-file=values-dagster.yaml=$dagsterValues `
    --from-file=values-airbyte.yaml=$airbyteValues `
    --dry-run=client -o yaml |
    kubectl apply -f -

Write-Host ""
Write-Host "==> Trigger an upgrade with one of:"
Write-Host "  kubectl delete job kserve-install   -n helm-runner --ignore-not-found"
Write-Host "  kubectl delete job dagster-upgrade  -n helm-runner --ignore-not-found"
Write-Host "  kubectl delete job airbyte-upgrade  -n helm-runner --ignore-not-found"
Write-Host "  kubectl apply  -f kubernetes\bootstrap\helm-runner\job-kserve.yaml"
Write-Host "  kubectl apply  -f kubernetes\bootstrap\helm-runner\job-dagster.yaml"
Write-Host "  kubectl apply  -f kubernetes\bootstrap\helm-runner\job-airbyte.yaml"
Write-Host "  kubectl wait   -n helm-runner --for=condition=Complete job/kserve-install --timeout=600s"
