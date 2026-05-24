#!/usr/bin/env bash
# =============================================================================
# Install Flink + Kafka Streaming Platform
# =============================================================================
# Installs the Strimzi Kafka Operator, Kafka cluster (KRaft), Kafka users,
# Kafka Connect, Kafka Bridge, Apicurio Schema Registry, Flink Kubernetes
# Operator, and Flink session cluster on the k3s cluster.
#
# Flags:
#   --with-java-jobs   Also apply FlinkSessionJob CRs for the Java TA-Lib jobs
#                      (kubernetes/base-services/flink/jobs-java/).
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - helm v3 installed
#   - MinIO running in data-services namespace
#   - PostgreSQL running in data-services namespace
#
# Usage: bash bootstrap/scripts/install-flink.sh [--with-java-jobs]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

WITH_JAVA_JOBS=0
for arg in "$@"; do
    case "${arg}" in
        --with-java-jobs) WITH_JAVA_JOBS=1 ;;
    esac
done

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---------------------------------------------------------------------------
# Step 0: Verify prerequisites
# ---------------------------------------------------------------------------
info "Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || error "kubectl not found"
command -v helm    >/dev/null 2>&1 || error "helm not found"
kubectl cluster-info >/dev/null 2>&1 || error "Cannot reach Kubernetes cluster"
info "Prerequisites OK."

# ---------------------------------------------------------------------------
# Step 1: Create namespaces
# ---------------------------------------------------------------------------
info "Ensuring namespaces exist..."
kubectl apply -f "${REPO_ROOT}/kubernetes/namespaces/namespaces.yaml"

# ---------------------------------------------------------------------------
# Step 2: Install Strimzi Kafka Operator via Helm
# ---------------------------------------------------------------------------
info "Installing Strimzi Kafka Operator..."
helm repo add strimzi https://strimzi.io/charts/ 2>/dev/null || true
helm repo update strimzi

if helm status strimzi-kafka-operator -n aqp-data-services >/dev/null 2>&1; then
    info "Strimzi Kafka Operator already installed, upgrading..."
    helm upgrade strimzi-kafka-operator strimzi/strimzi-kafka-operator \
        --namespace aqp-data-services \
        -f "${REPO_ROOT}/kubernetes/base-services/kafka/values.yaml" \
        --wait --timeout 5m
else
    helm install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
        --namespace aqp-data-services \
        -f "${REPO_ROOT}/kubernetes/base-services/kafka/values.yaml" \
        --wait --timeout 5m
fi
info "Strimzi Kafka Operator installed."

# ---------------------------------------------------------------------------
# Step 3: Deploy Kafka cluster + topics
# ---------------------------------------------------------------------------
info "Deploying Kafka cluster (KRaft mode)..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/kafka/kafka-cluster.yaml"

info "Waiting for Kafka cluster to become ready (this may take a few minutes)..."
kubectl wait kafka/trading-kafka \
    --for=condition=Ready \
    --namespace aqp-data-services \
    --timeout=600s 2>/dev/null || warn "Kafka cluster not ready yet; topics may be applied once it is."

info "Creating Kafka topics..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/kafka/topics.yaml"

# ---------------------------------------------------------------------------
# Step 3.1: Apply Kafka users (SCRAM credentials via User Operator)
# ---------------------------------------------------------------------------
info "Applying KafkaUser CRs (SCRAM credentials materialized by User Operator)..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/kafka/users.yaml"

info "Waiting for user SCRAM secrets to materialize..."
for user in producer-market producer-features consumer-flink consumer-management connect-sinks bridge-gateway admin-sdk; do
    kubectl wait --for=condition=Ready kafkauser/${user} \
        --namespace aqp-data-services --timeout=180s 2>/dev/null || \
        warn "KafkaUser ${user} not Ready yet; Connect/Bridge will retry."
done

# ---------------------------------------------------------------------------
# Step 3.2: Apply Schema Registry (Apicurio, Kafka-backed storage)
# ---------------------------------------------------------------------------
info "Deploying Apicurio Schema Registry..."
kubectl apply -k "${REPO_ROOT}/kubernetes/base-services/schema-registry/"

# ---------------------------------------------------------------------------
# Step 3.3: Apply Kafka Connect, Bridge, MirrorMaker 2, Rebalance template
# ---------------------------------------------------------------------------
info "Deploying Kafka Connect cluster..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/kafka/connect.yaml"

info "Deploying Kafka Bridge..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/kafka/bridge.yaml"

info "Applying MirrorMaker 2 template (replicas=0, review before activating)..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/kafka/mirrormaker2.yaml" || \
    warn "MirrorMaker 2 apply failed (expected until a target cluster is configured)."

info "Applying KafkaRebalance template (paused)..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/kafka/rebalance.yaml" || \
    warn "KafkaRebalance apply failed (expected until Cruise Control is enabled)."

info "Applying sample KafkaConnector CRs (paused)..."
kubectl apply -k "${REPO_ROOT}/kubernetes/base-services/kafka/connectors/" || \
    warn "Connector apply failed (will be retried once Connect is Ready)."

# ---------------------------------------------------------------------------
# Step 4: Install Flink Kubernetes Operator via Helm
# ---------------------------------------------------------------------------
info "Installing Flink Kubernetes Operator v1.14.0..."
helm repo add flink-operator-repo \
    https://downloads.apache.org/flink/flink-kubernetes-operator-1.14.0/ 2>/dev/null || true
helm repo update flink-operator-repo

if helm status flink-kubernetes-operator -n aqp-streaming >/dev/null 2>&1; then
    info "Flink Operator already installed, upgrading..."
    helm upgrade flink-kubernetes-operator \
        flink-operator-repo/flink-kubernetes-operator \
        --namespace aqp-streaming \
        -f "${REPO_ROOT}/kubernetes/base-services/flink/values.yaml" \
        --wait --timeout 5m
else
    helm install flink-kubernetes-operator \
        flink-operator-repo/flink-kubernetes-operator \
        --namespace aqp-streaming --create-namespace \
        -f "${REPO_ROOT}/kubernetes/base-services/flink/values.yaml" \
        --wait --timeout 5m
fi
info "Flink Kubernetes Operator installed."

# ---------------------------------------------------------------------------
# Step 5: Apply Flink RBAC, config, session cluster
# ---------------------------------------------------------------------------
info "Applying Flink RBAC and configuration..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/flink/rbac.yaml"
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/flink/flink-configmap.yaml"
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/flink/flink-postgres-init.yaml"
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/flink/service.yaml"
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/flink/ingress.yaml"

info "Deploying Flink session cluster..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/flink/session-cluster.yaml"

info "Applying placeholder PyFlink FlinkSessionJob manifests (suspended)..."
kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/flink/jobs/"

if [ "${WITH_JAVA_JOBS}" -eq 1 ]; then
    if [ -d "${REPO_ROOT}/kubernetes/base-services/flink/jobs-java" ]; then
        info "Applying Java TA-Lib FlinkSessionJob manifests (suspended)..."
        kubectl apply -f "${REPO_ROOT}/kubernetes/base-services/flink/jobs-java/"
    else
        warn "--with-java-jobs flag set but jobs-java/ directory does not exist yet."
    fi
fi

# ---------------------------------------------------------------------------
# Step 6: Apply ServiceMonitors and Grafana dashboard
# ---------------------------------------------------------------------------
info "Applying ServiceMonitors for Flink and Kafka..."
kubectl apply -f "${REPO_ROOT}/kubernetes/observability/prometheus/servicemonitors.yaml"

info "Applying Grafana Flink dashboard..."
kubectl apply -f "${REPO_ROOT}/kubernetes/observability/grafana/flink-dashboard-configmap.yaml"

# ---------------------------------------------------------------------------
# Step 7: Initialize PostgreSQL schema
# ---------------------------------------------------------------------------
info "Initializing Flink trading tables in PostgreSQL..."
FLINK_SQL=$(kubectl get configmap flink-postgres-init -n aqp-streaming -o jsonpath='{.data.flink-init\.sql}' 2>/dev/null || echo "")
if [ -n "${FLINK_SQL}" ]; then
    kubectl exec -n aqp-data-services deploy/postgresql -- \
        psql -U postgres -c "${FLINK_SQL}" 2>/dev/null || \
        warn "Could not auto-initialize PostgreSQL schema. Run manually:\n  kubectl exec -n aqp-data-services deploy/postgresql -- psql -U postgres < flink-init.sql"
fi

# ---------------------------------------------------------------------------
# Step 8: Verify
# ---------------------------------------------------------------------------
info "Verifying deployment status..."
echo ""
echo "=== Strimzi / Kafka ==="
kubectl get pods -n aqp-data-services -l strimzi.io/cluster=trading-kafka 2>/dev/null || echo "  (no Kafka pods yet)"
echo ""
echo "=== Kafka Topics ==="
kubectl get kafkatopics -n aqp-data-services 2>/dev/null || echo "  (topics pending)"
echo ""
echo "=== Kafka Users ==="
kubectl get kafkausers -n aqp-data-services 2>/dev/null || echo "  (users pending)"
echo ""
echo "=== Kafka Connect ==="
kubectl get kafkaconnect -n aqp-data-services 2>/dev/null || echo "  (connect pending)"
echo ""
echo "=== Kafka Connectors ==="
kubectl get kafkaconnectors -n aqp-data-services 2>/dev/null || echo "  (connectors pending)"
echo ""
echo "=== Kafka Bridge ==="
kubectl get kafkabridge -n aqp-data-services 2>/dev/null || echo "  (bridge pending)"
echo ""
echo "=== Schema Registry ==="
kubectl get pods -n aqp-data-services -l app=apicurio-registry 2>/dev/null || echo "  (registry pending)"
echo ""
echo "=== Flink Operator ==="
kubectl get pods -n aqp-streaming -l app.kubernetes.io/name=flink-kubernetes-operator 2>/dev/null || echo "  (operator pending)"
echo ""
echo "=== Flink Session Cluster ==="
kubectl get flinkdeployments -n aqp-streaming 2>/dev/null || echo "  (CRD not ready yet)"
echo ""
echo "=== Flink Session Jobs ==="
kubectl get flinksessionjobs -n aqp-streaming 2>/dev/null || echo "  (CRD not ready yet)"
echo ""

info "Streaming platform installation complete!"
info "Service URLs:"
echo "  Flink Web UI:        http://flink.local"
echo "  Schema Registry:     http://schema-registry.local"
echo "  Kafka Bridge:        http://kafka-bridge.local"
echo "  Kafka Bootstrap:     trading-kafka-kafka-bootstrap.data-services:9092 (plain, internal)"
echo "  Kafka Bootstrap TLS: trading-kafka-kafka-bootstrap.data-services:9094 (SCRAM, internal)"
echo ""
info "Add to your hosts file:  <CLUSTER_IP>  flink.local schema-registry.local kafka-bridge.local"
