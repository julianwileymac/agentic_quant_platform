# =============================================================================
# Grafana Port 3000 Conflict Resolver
# =============================================================================
# Version: 1.0.0
#
# Automates the process of fixing the Grafana port 3000 conflict caused by
# gpt-research or other processes occupying the port on the control plane.
#
# Usage:
#   .\fix-grafana.ps1                                    # Use defaults
#   .\fix-grafana.ps1 -ControlPlaneHost "julia@192.168.12.112"
#   .\fix-grafana.ps1 -ControlPlaneHost "julia@192.168.12.112" -DisableAutoStart
#   .\fix-grafana.ps1 -LocalMode                         # Run directly (on control plane)
#
# Prerequisites:
#   - SSH access to control plane (unless using -LocalMode)
#   - kubectl configured and working
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$ControlPlaneHost = "julia@192.168.12.112",

    [Parameter(Mandatory=$false)]
    [string]$SshKey = "",

    [Parameter(Mandatory=$false)]
    [string]$GrafanaNamespace = "observability",

    [Parameter(Mandatory=$false)]
    [int]$Port = 3000,

    [Parameter(Mandatory=$false)]
    [switch]$DisableAutoStart = $false,

    [Parameter(Mandatory=$false)]
    [switch]$LocalMode = $false,

    [Parameter(Mandatory=$false)]
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Continue"

# =============================================================================
# Helpers
# =============================================================================

function Write-Step {
    param([int]$Number, [string]$Message)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  Step $Number`: $Message" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Message)
    Write-Host "  [OK]   $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "  [INFO] $Message" -ForegroundColor White
}

function Invoke-RemoteCommand {
    param([string]$Command)

    if ($LocalMode) {
        try {
            $output = Invoke-Expression $Command 2>&1
            return @{ Success = ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE); Output = ($output -join "`n") }
        } catch {
            return @{ Success = $false; Output = $_.Exception.Message }
        }
    }

    $sshArgs = "-o StrictHostKeyChecking=no -o ConnectTimeout=10"
    if (-not [string]::IsNullOrEmpty($SshKey)) {
        $keyPath = $SshKey
        if ($keyPath.StartsWith("~")) { $keyPath = $keyPath.Replace("~", $HOME) }
        $sshArgs += " -i `"$keyPath`""
    }

    $sshCmd = "ssh $sshArgs $ControlPlaneHost `"$Command`""
    try {
        $output = Invoke-Expression $sshCmd 2>&1
        return @{ Success = ($LASTEXITCODE -eq 0); Output = ($output -join "`n") }
    } catch {
        return @{ Success = $false; Output = $_.Exception.Message }
    }
}

# =============================================================================
# Main
# =============================================================================

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "  Grafana Port $Port Conflict Resolver v1.0.0" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

if ($DryRun) {
    Write-Host "  ** DRY RUN MODE -- no changes will be made **" -ForegroundColor Yellow
    Write-Host ""
}

$mode = if ($LocalMode) { "Local" } else { "SSH to $ControlPlaneHost" }
Write-Info "Mode: $mode"

# -------------------------------------------------------------------------
# Step 1: Check what's using the port
# -------------------------------------------------------------------------
Write-Step 1 "Check what is using port $Port"

$result = Invoke-RemoteCommand "sudo lsof -i :$Port -n -P 2>/dev/null || echo 'PORT_FREE'"

if ($result.Output -match "PORT_FREE") {
    Write-OK "Port $Port is already free!"
    $portFree = $true
} else {
    Write-Info "Processes using port ${Port}:"
    $result.Output -split "`n" | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    $portFree = $false
}

# -------------------------------------------------------------------------
# Step 2: Check for gpt-research processes
# -------------------------------------------------------------------------
Write-Step 2 "Check for gpt-research processes"

$result = Invoke-RemoteCommand "pgrep -fa gpt-research 2>/dev/null || echo 'NONE_FOUND'"

if ($result.Output -match "NONE_FOUND") {
    Write-OK "No gpt-research processes found"
    $gptRunning = $false
} else {
    Write-Info "Found gpt-research processes:"
    $result.Output -split "`n" | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    $gptRunning = $true
}

# -------------------------------------------------------------------------
# Step 3: Kill processes on the port
# -------------------------------------------------------------------------
if (-not $portFree) {
    Write-Step 3 "Kill processes on port $Port"

    if ($DryRun) {
        Write-Info "Would kill: sudo pkill -9 -f gpt-research && sudo kill -9 `$(sudo lsof -t -i :$Port)"
    } else {
        # Kill gpt-research first
        if ($gptRunning) {
            Write-Info "Killing gpt-research processes..."
            $result = Invoke-RemoteCommand "sudo pkill -9 -f gpt-research 2>/dev/null; echo done"
            Write-OK "Sent kill signal to gpt-research"
        }

        # Kill anything remaining on the port
        Write-Info "Killing any remaining processes on port $Port..."
        $result = Invoke-RemoteCommand "sudo kill -9 `$(sudo lsof -t -i :$Port 2>/dev/null) 2>/dev/null; sleep 1; echo done"

        # Verify port is free
        Start-Sleep -Seconds 2
        $verify = Invoke-RemoteCommand "sudo lsof -i :$Port -n -P 2>/dev/null || echo 'PORT_FREE'"

        if ($verify.Output -match "PORT_FREE") {
            Write-OK "Port $Port is now free!"
        } else {
            Write-Fail "Port $Port is still in use. Manual intervention may be needed."
            Write-Info "Try: ssh $ControlPlaneHost `"sudo fuser -k ${Port}/tcp`""
        }
    }
} else {
    Write-Step 3 "Kill processes (skipped -- port already free)"
}

# -------------------------------------------------------------------------
# Step 4: Optionally disable gpt-research auto-start
# -------------------------------------------------------------------------
if ($DisableAutoStart) {
    Write-Step 4 "Disable gpt-research auto-start"

    if ($DryRun) {
        Write-Info "Would check and disable systemd service, crontab, autostart entries"
    } else {
        # Check systemd
        $result = Invoke-RemoteCommand "systemctl list-units --type=service 2>/dev/null | grep -i gpt || echo 'NO_SERVICE'"
        if ($result.Output -notmatch "NO_SERVICE") {
            Write-Info "Found systemd service. Disabling..."
            Invoke-RemoteCommand "sudo systemctl stop gpt-research 2>/dev/null; sudo systemctl disable gpt-research 2>/dev/null"
            Write-OK "Disabled gpt-research systemd service"
        } else {
            Write-OK "No gpt-research systemd service found"
        }

        # Check crontab
        $result = Invoke-RemoteCommand "crontab -l 2>/dev/null | grep -i gpt || echo 'NO_CRON'"
        if ($result.Output -notmatch "NO_CRON") {
            Write-Info "Found gpt-research in crontab:"
            Write-Host "    $($result.Output)" -ForegroundColor Yellow
            Write-Info "Remove manually with: ssh $ControlPlaneHost 'crontab -e'"
        } else {
            Write-OK "No gpt-research crontab entries found"
        }

        # Check autostart
        $result = Invoke-RemoteCommand "ls ~/.config/autostart/ 2>/dev/null | grep -i gpt || echo 'NO_AUTOSTART'"
        if ($result.Output -notmatch "NO_AUTOSTART") {
            Write-Info "Found autostart entry: $($result.Output)"
            Write-Info "Remove manually if desired"
        } else {
            Write-OK "No gpt-research autostart entries found"
        }
    }
}

# -------------------------------------------------------------------------
# Step 5: Restart Grafana pod
# -------------------------------------------------------------------------
Write-Step 5 "Restart Grafana pod"

# Get current grafana pod name
$getPodCmd = "kubectl get pods -n $GrafanaNamespace -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}' 2>/dev/null"
$podResult = Invoke-Expression $getPodCmd 2>&1

if ([string]::IsNullOrEmpty($podResult) -or $podResult -match "error") {
    # Try via SSH if local kubectl didn't work
    $podResult = Invoke-RemoteCommand $getPodCmd
    $grafanaPod = $podResult.Output.Trim().Trim("'")
} else {
    $grafanaPod = "$podResult".Trim().Trim("'")
}

if ([string]::IsNullOrEmpty($grafanaPod)) {
    Write-Fail "Could not find Grafana pod. Is the Helm chart installed?"
    Write-Info "Install with: helm upgrade --install prometheus prometheus-community/kube-prometheus-stack -n $GrafanaNamespace -f kubernetes/observability/prometheus/values.yaml"
} else {
    Write-Info "Found Grafana pod: $grafanaPod"

    if ($DryRun) {
        Write-Info "Would delete pod: kubectl delete pod -n $GrafanaNamespace $grafanaPod --force --grace-period=0"
    } else {
        Write-Info "Deleting pod to trigger restart..."
        $deleteCmd = "kubectl delete pod -n $GrafanaNamespace $grafanaPod --force --grace-period=0 2>&1"
        Invoke-Expression $deleteCmd | Out-Null
        Write-OK "Pod deleted, waiting for restart..."

        # Wait and check
        Write-Info "Waiting 20 seconds for pod to restart..."
        Start-Sleep -Seconds 20

        $statusResult = Invoke-Expression "kubectl get pods -n $GrafanaNamespace -l app.kubernetes.io/name=grafana 2>&1"
        Write-Info "Current Grafana pod status:"
        $statusResult -split "`n" | ForEach-Object { Write-Host "    $_" }
    }
}

# -------------------------------------------------------------------------
# Step 6: Verify
# -------------------------------------------------------------------------
Write-Step 6 "Verify Grafana recovery"

if (-not $DryRun) {
    Start-Sleep -Seconds 5

    # Check pod status
    $statusResult = Invoke-Expression "kubectl get pods -n $GrafanaNamespace -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].status.phase}' 2>&1"
    $phase = "$statusResult".Trim().Trim("'")

    if ($phase -eq "Running") {
        Write-OK "Grafana pod is Running!"
    } else {
        Write-Info "Grafana pod phase: $phase (may still be starting)"
        Write-Info "Monitor with: kubectl get pods -n $GrafanaNamespace -l app.kubernetes.io/name=grafana -w"
    }

    # Check port
    $portCheck = Invoke-RemoteCommand "curl -s -o /dev/null -w '%{http_code}' http://localhost:$Port 2>/dev/null || echo 'UNREACHABLE'"
    if ($portCheck.Output -match "302|200") {
        Write-OK "Grafana is responding on port $Port!"
    } else {
        Write-Info "Grafana not yet responding on port $Port (status: $($portCheck.Output))"
        Write-Info "It may take another minute to fully start up."
    }
}

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor $(if ($DryRun) { "Yellow" } else { "Green" })
Write-Host "  Fix Complete" -ForegroundColor $(if ($DryRun) { "Yellow" } else { "Green" })
Write-Host ("=" * 70) -ForegroundColor $(if ($DryRun) { "Yellow" } else { "Green" })
Write-Host ""
Write-Info "Access Grafana at: http://192.168.12.112:$Port"
Write-Info "Credentials: admin / admin123"
Write-Host ""
