#!/usr/bin/env bash
# =============================================================================
# Install Flink + Kafka Streaming Platform (AQP-owned)
# =============================================================================
# Installs Strimzi, Kafka (KRaft), users, Connect, Bridge, Schema Registry,
# Flink Kubernetes Operator, and the Flink session cluster under aqp-* namespaces.
#
# Flags:
#   --with-java-jobs   Also apply FlinkSessionJob CRs for Java TA-Lib jobs
#                      (deployments/kubernetes/base-services/flink/jobs-java/).
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - helm v3 installed
#   - MinIO + Postgres running in aqp-data-services (apply shared infra first)
#
# Usage: bash aqp_platform/scripts/cluster_install/install-flink.sh [--with-java-jobs]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
K8S_ROOT="${REPO_ROOT}/deployments/kubernetes"
KAFKA_DIR="${K8S_ROOT}/base-services/kafka-strimzi"
FLINK_DIR="${K8S_ROOT}/base-services/flink"
SCHEMA_DIR="${K8S_ROOT}/base-services/schema-registry"

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

info "Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || error "kubectl not found"
command -v helm    >/dev/null 2>&1 || error "helm not found"
kubectl cluster-info >/dev/null 2>&1 || error "Cannot reach Kubernetes cluster"
info "Prerequisites OK."

info "Ensuring AQP shared namespaces exist..."
kubectl apply -f "${K8S_ROOT}/base/namespaces-shared.yaml"

info "Installing Strimzi Kafka Operator..."
helm repo add strimzi https://strimzi.io/charts/ 2>/dev/null || true
helm repo update strimzi

if helm status strimzi-kafka-operator -n aqp-streaming >/dev/null 2>&1; then
    info "Strimzi Kafka Operator already installed, upgrading..."
    helm upgrade strimzi-kafka-operator strimzi/strimzi-kafka-operator \
        --namespace aqp-streaming \
        -f "${KAFKA_DIR}/values.yaml" \
        --wait --timeout 5m
else
    helm install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
        --namespace aqp-streaming --create-namespace \
        -f "${KAFKA_DIR}/values.yaml" \
        --wait --timeout 5m
fi
info "Strimzi Kafka Operator installed."

info "Deploying Kafka cluster + topics + users + connect stack..."
kubectl apply -f "${KAFKA_DIR}/kafka-cluster.yaml"
kubectl wait kafka/trading-kafka \
    --for=condition=Ready \
    --namespace aqp-streaming \
    --timeout=600s 2>/dev/null || warn "Kafka cluster not ready yet; continuing."
kubectl apply -f "${KAFKA_DIR}/topics.yaml"
kubectl apply -f "${KAFKA_DIR}/users.yaml"

info "Waiting for KafkaUser SCRAM secrets..."
for user in producer-market producer-features consumer-flink consumer-management connect-sinks bridge-gateway admin-sdk; do
    kubectl wait --for=condition=Ready kafkauser/${user} \
        --namespace aqp-streaming --timeout=180s 2>/dev/null || \
        warn "KafkaUser ${user} not Ready yet."
done

info "Deploying Apicurio Schema Registry..."
kubectl apply -k "${SCHEMA_DIR}/"

info "Deploying Kafka Connect + Bridge + optional MM2 / rebalance templates..."
kubectl apply -f "${KAFKA_DIR}/connect.yaml"
kubectl apply -f "${KAFKA_DIR}/bridge.yaml"
kubectl apply -f "${KAFKA_DIR}/mirrormaker2.yaml" 2>/dev/null || \
    warn "MirrorMaker 2 apply skipped (configure target cluster first)."
kubectl apply -f "${KAFKA_DIR}/rebalance.yaml" 2>/dev/null || \
    warn "KafkaRebalance apply skipped (Cruise Control may be disabled)."
kubectl apply -k "${KAFKA_DIR}/connectors/" 2>/dev/null || \
    warn "KafkaConnector apply skipped until Connect is Ready."

info "Installing Flink Kubernetes Operator v1.14.0..."
helm repo add flink-operator-repo \
    https://downloads.apache.org/flink/flink-kubernetes-operator-1.14.0/ 2>/dev/null || true
helm repo update flink-operator-repo

if helm status flink-kubernetes-operator -n aqp-streaming >/dev/null 2>&1; then
    helm upgrade flink-kubernetes-operator \
        flink-operator-repo/flink-kubernetes-operator \
        --namespace aqp-streaming \
        -f "${FLINK_DIR}/values.yaml" \
        --wait --timeout 5m
else
    helm install flink-kubernetes-operator \
        flink-operator-repo/flink-kubernetes-operator \
        --namespace aqp-streaming \
        -f "${FLINK_DIR}/values.yaml" \
        --wait --timeout 5m
fi

info "Applying Flink session cluster + suspended PyFlink jobs..."
kubectl apply -k "${FLINK_DIR}/"

if [ "${WITH_JAVA_JOBS}" -eq 1 ]; then
    if [ -d "${FLINK_DIR}/jobs-java" ]; then
        info "Applying Java TA-Lib FlinkSessionJob manifests..."
        kubectl apply -k "${FLINK_DIR}/jobs-java/"
    else
        warn "--with-java-jobs set but ${FLINK_DIR}/jobs-java/ does not exist."
    fi
fi

info "Initializing Flink trading tables in PostgreSQL (best-effort)..."
FLINK_SQL=$(kubectl get configmap flink-postgres-init -n aqp-streaming -o jsonpath='{.data.flink-init\.sql}' 2>/dev/null || echo "")
if [ -n "${FLINK_SQL}" ]; then
    kubectl exec -n aqp-data-services deploy/postgresql -- \
        psql -U postgres -c "${FLINK_SQL}" 2>/dev/null || \
        warn "Could not auto-initialize PostgreSQL schema; apply flink-init.sql manually."
fi

info "Streaming platform installation complete."
info "Service URLs (after ingress/DNS): Flink UI, Schema Registry, Kafka Bridge — see aqp_docs/streaming.md"
