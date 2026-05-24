# =============================================================================
# Install Flink + Kafka Streaming Platform (PowerShell)
# =============================================================================
# Installs the Strimzi Kafka Operator, Kafka cluster (KRaft), Kafka users,
# Kafka Connect, Kafka Bridge, Apicurio Schema Registry, Flink Kubernetes
# Operator, and Flink session cluster on the k3s cluster.
#
# Flags:
#   -WithJavaJobs   Also apply FlinkSessionJob CRs for the Java TA-Lib jobs
#                   (kubernetes\base-services\flink\jobs-java\).
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - helm v3 installed
#   - MinIO running in data-services namespace
#   - PostgreSQL running in data-services namespace
#
# Usage: .\bootstrap\scripts\install-flink.ps1 [-WithJavaJobs]
# =============================================================================

param(
    [switch] $WithJavaJobs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = (Resolve-Path "$ScriptDir\..\..").Path

function Write-Info  { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Step 0: Verify prerequisites
# ---------------------------------------------------------------------------
Write-Info "Checking prerequisites..."
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) { Write-Err "kubectl not found" }
if (-not (Get-Command helm -ErrorAction SilentlyContinue))    { Write-Err "helm not found" }
kubectl cluster-info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Err "Cannot reach Kubernetes cluster" }
Write-Info "Prerequisites OK."

# ---------------------------------------------------------------------------
# Step 1: Create namespaces
# ---------------------------------------------------------------------------
Write-Info "Ensuring namespaces exist..."
kubectl apply -f "$RepoRoot\kubernetes\namespaces\namespaces.yaml"

# ---------------------------------------------------------------------------
# Step 2: Install Strimzi Kafka Operator via Helm
# ---------------------------------------------------------------------------
Write-Info "Installing Strimzi Kafka Operator..."
helm repo add strimzi https://strimzi.io/charts/ 2>$null
helm repo update strimzi

$strimziStatus = helm status strimzi-kafka-operator -n aqp-data-services 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Info "Strimzi Kafka Operator already installed, upgrading..."
    helm upgrade strimzi-kafka-operator strimzi/strimzi-kafka-operator `
        --namespace aqp-data-services `
        -f "$RepoRoot\kubernetes\base-services\kafka\values.yaml" `
        --wait --timeout 5m0s
} else {
    helm install strimzi-kafka-operator strimzi/strimzi-kafka-operator `
        --namespace aqp-data-services `
        -f "$RepoRoot\kubernetes\base-services\kafka\values.yaml" `
        --wait --timeout 5m0s
}
Write-Info "Strimzi Kafka Operator installed."

# ---------------------------------------------------------------------------
# Step 3: Deploy Kafka cluster + topics
# ---------------------------------------------------------------------------
Write-Info "Deploying Kafka cluster (KRaft mode)..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\kafka\kafka-cluster.yaml"

Write-Info "Waiting for Kafka cluster to become ready..."
kubectl wait kafka/trading-kafka `
    --for=condition=Ready `
    --namespace aqp-data-services `
    --timeout=600s 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warn "Kafka cluster not ready yet; topics may be applied once it is." }

Write-Info "Creating Kafka topics..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\kafka\topics.yaml"

# ---------------------------------------------------------------------------
# Step 3.1: Apply Kafka users (SCRAM credentials via User Operator)
# ---------------------------------------------------------------------------
Write-Info "Applying KafkaUser CRs (SCRAM credentials materialized by User Operator)..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\kafka\users.yaml"

Write-Info "Waiting for user SCRAM secrets to materialize..."
$users = @("producer-market","producer-features","consumer-flink","consumer-management","connect-sinks","bridge-gateway","admin-sdk")
foreach ($user in $users) {
    kubectl wait --for=condition=Ready kafkauser/$user --namespace aqp-data-services --timeout=180s 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Warn "KafkaUser $user not Ready yet; Connect/Bridge will retry." }
}

# ---------------------------------------------------------------------------
# Step 3.2: Apply Schema Registry (Apicurio, Kafka-backed storage)
# ---------------------------------------------------------------------------
Write-Info "Deploying Apicurio Schema Registry..."
kubectl apply -k "$RepoRoot\kubernetes\base-services\schema-registry\"

# ---------------------------------------------------------------------------
# Step 3.3: Apply Kafka Connect, Bridge, MirrorMaker 2, Rebalance template
# ---------------------------------------------------------------------------
Write-Info "Deploying Kafka Connect cluster..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\kafka\connect.yaml"

Write-Info "Deploying Kafka Bridge..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\kafka\bridge.yaml"

Write-Info "Applying MirrorMaker 2 template (replicas=0, review before activating)..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\kafka\mirrormaker2.yaml" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warn "MirrorMaker 2 apply failed (expected until a target cluster is configured)." }

Write-Info "Applying KafkaRebalance template (paused)..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\kafka\rebalance.yaml" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warn "KafkaRebalance apply failed (expected until Cruise Control is enabled)." }

Write-Info "Applying sample KafkaConnector CRs (paused)..."
kubectl apply -k "$RepoRoot\kubernetes\base-services\kafka\connectors\" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warn "Connector apply failed (will be retried once Connect is Ready)." }

# ---------------------------------------------------------------------------
# Step 4: Install Flink Kubernetes Operator via Helm
# ---------------------------------------------------------------------------
Write-Info "Installing Flink Kubernetes Operator v1.14.0..."
helm repo add flink-operator-repo `
    https://downloads.apache.org/flink/flink-kubernetes-operator-1.14.0/ 2>$null
helm repo update flink-operator-repo

$flinkStatus = helm status flink-kubernetes-operator -n aqp-streaming 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Info "Flink Operator already installed, upgrading..."
    helm upgrade flink-kubernetes-operator `
        flink-operator-repo/flink-kubernetes-operator `
        --namespace aqp-streaming `
        -f "$RepoRoot\kubernetes\base-services\flink\values.yaml" `
        --wait --timeout 5m0s
} else {
    helm install flink-kubernetes-operator `
        flink-operator-repo/flink-kubernetes-operator `
        --namespace aqp-streaming --create-namespace `
        -f "$RepoRoot\kubernetes\base-services\flink\values.yaml" `
        --wait --timeout 5m0s
}
Write-Info "Flink Kubernetes Operator installed."

# ---------------------------------------------------------------------------
# Step 5: Apply Flink RBAC, config, session cluster
# ---------------------------------------------------------------------------
Write-Info "Applying Flink RBAC and configuration..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\flink\rbac.yaml"
kubectl apply -f "$RepoRoot\kubernetes\base-services\flink\flink-configmap.yaml"
kubectl apply -f "$RepoRoot\kubernetes\base-services\flink\flink-postgres-init.yaml"
kubectl apply -f "$RepoRoot\kubernetes\base-services\flink\service.yaml"
kubectl apply -f "$RepoRoot\kubernetes\base-services\flink\ingress.yaml"

Write-Info "Deploying Flink session cluster..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\flink\session-cluster.yaml"

Write-Info "Applying placeholder PyFlink FlinkSessionJob manifests (suspended)..."
kubectl apply -f "$RepoRoot\kubernetes\base-services\flink\jobs\"

if ($WithJavaJobs) {
    if (Test-Path "$RepoRoot\kubernetes\base-services\flink\jobs-java") {
        Write-Info "Applying Java TA-Lib FlinkSessionJob manifests (suspended)..."
        kubectl apply -f "$RepoRoot\kubernetes\base-services\flink\jobs-java\"
    } else {
        Write-Warn "-WithJavaJobs flag set but jobs-java\ directory does not exist yet."
    }
}

# ---------------------------------------------------------------------------
# Step 6: Apply ServiceMonitors and Grafana dashboard
# ---------------------------------------------------------------------------
Write-Info "Applying ServiceMonitors for Flink and Kafka..."
kubectl apply -f "$RepoRoot\kubernetes\observability\prometheus\servicemonitors.yaml"

Write-Info "Applying Grafana Flink dashboard..."
kubectl apply -f "$RepoRoot\kubernetes\observability\grafana\flink-dashboard-configmap.yaml"

# ---------------------------------------------------------------------------
# Step 7: Verify
# ---------------------------------------------------------------------------
Write-Info "Verifying deployment status..."
Write-Host ""
Write-Host "=== Strimzi / Kafka ===" -ForegroundColor Cyan
kubectl get pods -n aqp-data-services -l strimzi.io/cluster=trading-kafka 2>$null
Write-Host ""
Write-Host "=== Kafka Topics ===" -ForegroundColor Cyan
kubectl get kafkatopics -n aqp-data-services 2>$null
Write-Host ""
Write-Host "=== Kafka Users ===" -ForegroundColor Cyan
kubectl get kafkausers -n aqp-data-services 2>$null
Write-Host ""
Write-Host "=== Kafka Connect ===" -ForegroundColor Cyan
kubectl get kafkaconnect -n aqp-data-services 2>$null
Write-Host ""
Write-Host "=== Kafka Connectors ===" -ForegroundColor Cyan
kubectl get kafkaconnectors -n aqp-data-services 2>$null
Write-Host ""
Write-Host "=== Kafka Bridge ===" -ForegroundColor Cyan
kubectl get kafkabridge -n aqp-data-services 2>$null
Write-Host ""
Write-Host "=== Schema Registry ===" -ForegroundColor Cyan
kubectl get pods -n aqp-data-services -l app=apicurio-registry 2>$null
Write-Host ""
Write-Host "=== Flink Operator ===" -ForegroundColor Cyan
kubectl get pods -n aqp-streaming -l app.kubernetes.io/name=flink-kubernetes-operator 2>$null
Write-Host ""
Write-Host "=== Flink Session Cluster ===" -ForegroundColor Cyan
kubectl get flinkdeployments -n aqp-streaming 2>$null
Write-Host ""
Write-Host "=== Flink Session Jobs ===" -ForegroundColor Cyan
kubectl get flinksessionjobs -n aqp-streaming 2>$null
Write-Host ""

Write-Info "Streaming platform installation complete!"
Write-Info "Service URLs:"
Write-Host "  Flink Web UI:        http://flink.local"
Write-Host "  Schema Registry:     http://schema-registry.local"
Write-Host "  Kafka Bridge:        http://kafka-bridge.local"
Write-Host "  Kafka Bootstrap:     trading-kafka-kafka-bootstrap.data-services:9092 (plain, internal)"
Write-Host "  Kafka Bootstrap TLS: trading-kafka-kafka-bootstrap.data-services:9094 (SCRAM, internal)"
Write-Host ""
Write-Info "Add to your hosts file:  <CLUSTER_IP>  flink.local schema-registry.local kafka-bridge.local"
