#!/bin/bash
# =============================================================================
# Minio Endpoint Health Check and Verification Script
# =============================================================================
# Verifies that Minio is properly deployed, accessible, and healthy.
#
# Usage:
#   ./verify-minio.sh [OPTIONS]
#
# Options:
#   --namespace NAMESPACE    Kubernetes namespace (default: data-services)
#   --host HOST             Hostname for ingress (default: minio.local)
#   --api-host API_HOST     Hostname for S3 API ingress (default: s3.local)
#   --verbose               Enable verbose output
#   --skip-ingress          Skip ingress verification
#   --skip-loadbalancer     Skip LoadBalancer verification
# =============================================================================

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-data-services}"
HOST="${HOST:-minio.local}"
API_HOST="${API_HOST:-s3.local}"
VERBOSE="${VERBOSE:-false}"
SKIP_INGRESS="${SKIP_INGRESS:-false}"
SKIP_LOADBALANCER="${SKIP_LOADBALANCER:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${CYAN}[VERBOSE]${NC} $1"
    fi
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --host)
                HOST="$2"
                shift 2
                ;;
            --api-host)
                API_HOST="$2"
                shift 2
                ;;
            --verbose)
                VERBOSE="true"
                shift
                ;;
            --skip-ingress)
                SKIP_INGRESS="true"
                shift
                ;;
            --skip-loadbalancer)
                SKIP_LOADBALANCER="true"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
}

# Check if pod is running
check_pod_status() {
    log_info "Checking Minio pod status"
    
    local status=$(kubectl get pod -n "$NAMESPACE" -l app=minio -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")
    
    if [[ "$status" == "Running" ]]; then
        log_success "Minio pod is running"
        
        # Get pod name for details
        local pod_name=$(kubectl get pod -n "$NAMESPACE" -l app=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [[ -n "$pod_name" ]]; then
            log_verbose "Pod name: $pod_name"
        fi
        return 0
    elif [[ "$status" == "NotFound" ]]; then
        log_error "Minio pod not found"
        return 1
    else
        log_warning "Minio pod status: $status"
        return 1
    fi
}

# Check service endpoints
check_service_endpoints() {
    log_info "Checking Minio service endpoints"
    
    local endpoints=$(kubectl get endpoints -n "$NAMESPACE" minio -o jsonpath='{.subsets[0].addresses[*].ip}' 2>/dev/null || echo "")
    
    if [[ -z "$endpoints" ]]; then
        log_error "Minio service has no endpoints"
        return 1
    else
        log_success "Minio service has endpoints: $endpoints"
        return 0
    fi
}

# Test Minio health endpoints
test_health_endpoints() {
    log_info "Testing Minio health endpoints"
    
    local pod_name=$(kubectl get pod -n "$NAMESPACE" -l app=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    
    if [[ -z "$pod_name" ]]; then
        log_error "Cannot test health endpoints: pod not found"
        return 1
    fi
    
    # Test liveness endpoint
    log_verbose "Testing liveness endpoint"
    local live_status=$(kubectl exec -n "$NAMESPACE" "$pod_name" -- \
        curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/live 2>/dev/null || echo "000")
    
    if [[ "$live_status" == "200" ]]; then
        log_success "Liveness endpoint returned HTTP 200"
    else
        log_warning "Liveness endpoint returned HTTP $live_status"
    fi
    
    # Test readiness endpoint
    log_verbose "Testing readiness endpoint"
    local ready_status=$(kubectl exec -n "$NAMESPACE" "$pod_name" -- \
        curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/ready 2>/dev/null || echo "000")
    
    if [[ "$ready_status" == "200" ]]; then
        log_success "Readiness endpoint returned HTTP 200"
    else
        log_warning "Readiness endpoint returned HTTP $ready_status"
    fi
    
    if [[ "$live_status" == "200" ]] && [[ "$ready_status" == "200" ]]; then
        return 0
    else
        return 1
    fi
}

# Check ingress resources
check_ingress() {
    log_info "Checking Minio ingress resources"
    
    # Check console ingress
    local console_ingress=$(kubectl get ingress -n "$NAMESPACE" minio-console -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$console_ingress" ]]; then
        log_success "Console ingress exists: minio-console"
        
        local ingress_address=$(kubectl get ingress -n "$NAMESPACE" minio-console -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
        if [[ -n "$ingress_address" ]]; then
            log_success "Console ingress address: $ingress_address"
        fi
    else
        log_warning "Console ingress not found"
    fi
    
    # Check API ingress
    local api_ingress=$(kubectl get ingress -n "$NAMESPACE" minio-api -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$api_ingress" ]]; then
        log_success "API ingress exists: minio-api"
        
        local ingress_address=$(kubectl get ingress -n "$NAMESPACE" minio-api -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
        if [[ -n "$ingress_address" ]]; then
            log_success "API ingress address: $ingress_address"
        fi
    else
        log_warning "API ingress not found"
    fi
    
    if [[ -n "$console_ingress" ]] || [[ -n "$api_ingress" ]]; then
        return 0
    else
        return 1
    fi
}

# Test ingress connectivity
test_ingress_connectivity() {
    log_info "Testing ingress connectivity"
    
    # Get ingress controller LoadBalancer IP
    local ingress_ip=$(kubectl get svc -n ingress ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    
    if [[ -z "$ingress_ip" ]]; then
        log_warning "Cannot test ingress connectivity: LoadBalancer IP not available"
        return 1
    fi
    
    if ! command -v curl &> /dev/null; then
        log_warning "curl not available, skipping connectivity test"
        return 1
    fi
    
    # Test console ingress
    log_verbose "Testing console ingress: http://$HOST"
    local console_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --resolve "$HOST:80:$ingress_ip" \
        --max-time 10 \
        "http://$HOST/" || echo "000")
    
    if [[ "$console_code" == "200" ]] || [[ "$console_code" == "301" ]] || [[ "$console_code" == "302" ]]; then
        log_success "Console ingress connectivity test passed (HTTP $console_code)"
    else
        log_warning "Console ingress connectivity test returned HTTP $console_code"
    fi
    
    # Test API ingress
    log_verbose "Testing API ingress: http://$API_HOST"
    local api_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --resolve "$API_HOST:80:$ingress_ip" \
        --max-time 10 \
        "http://$API_HOST/" || echo "000")
    
    if [[ "$api_code" == "200" ]] || [[ "$api_code" == "403" ]] || [[ "$api_code" == "404" ]]; then
        log_success "API ingress connectivity test passed (HTTP $api_code)"
    else
        log_warning "API ingress connectivity test returned HTTP $api_code"
    fi
    
    return 0
}

# Check LoadBalancer service
check_loadbalancer_service() {
    log_info "Checking LoadBalancer service: minio-external"
    
    local lb_exists=$(kubectl get svc -n "$NAMESPACE" minio-external -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")
    
    if [[ -z "$lb_exists" ]]; then
        log_error "LoadBalancer service minio-external not found"
        return 1
    fi
    
    log_success "LoadBalancer service exists"
    
    # Check LoadBalancer IP
    local lb_ip=$(kubectl get svc -n "$NAMESPACE" minio-external -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    
    if [[ -n "$lb_ip" ]]; then
        log_success "LoadBalancer IP: $lb_ip"
        
        # Test connectivity
        if command -v curl &> /dev/null && [[ "$SKIP_LOADBALANCER" != "true" ]]; then
            # Test API port
            log_info "Testing LoadBalancer API connectivity on port 9000"
            local api_code=$(curl -s -o /dev/null -w "%{http_code}" \
                --max-time 10 \
                "http://$lb_ip:9000/minio/health/live" || echo "000")
            
            if [[ "$api_code" == "200" ]]; then
                log_success "LoadBalancer API connectivity test passed (HTTP $api_code)"
            else
                log_warning "LoadBalancer API connectivity test returned HTTP $api_code"
            fi
            
            # Test console port
            log_info "Testing LoadBalancer console connectivity on port 9001"
            local console_code=$(curl -s -o /dev/null -w "%{http_code}" \
                --max-time 10 \
                "http://$lb_ip:9001/" || echo "000")
            
            if [[ "$console_code" == "200" ]] || [[ "$console_code" == "301" ]] || [[ "$console_code" == "302" ]]; then
                log_success "LoadBalancer console connectivity test passed (HTTP $console_code)"
            else
                log_warning "LoadBalancer console connectivity test returned HTTP $console_code"
            fi
        fi
        
        return 0
    else
        log_warning "LoadBalancer IP not assigned yet (may take a few minutes)"
        return 1
    fi
}

# Display access information
display_access_info() {
    echo ""
    log_info "=== Minio Access Information ==="
    
    # Ingress access
    local ingress_ip=$(kubectl get svc -n ingress ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [[ -n "$ingress_ip" ]]; then
        echo ""
        log_info "Ingress Access:"
        echo "  Console: http://$HOST"
        echo "  API: http://$API_HOST"
        echo "  Direct IP: http://$ingress_ip (add Host header)"
        echo ""
        log_info "To access via ingress, ensure hosts resolve to $ingress_ip"
        log_info "Add to /etc/hosts:"
        echo "  $ingress_ip  $HOST"
        echo "  $ingress_ip  $API_HOST"
    fi
    
    # LoadBalancer access
    local lb_ip=$(kubectl get svc -n "$NAMESPACE" minio-external -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [[ -n "$lb_ip" ]]; then
        echo ""
        log_info "LoadBalancer Access:"
        echo "  Console: http://$lb_ip:9001"
        echo "  API: http://$lb_ip:9000"
        echo ""
        log_info "Default credentials: minioadmin / minioadmin123"
    fi
    
    # ClusterIP access (for debugging)
    local cluster_ip=$(kubectl get svc -n "$NAMESPACE" minio -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
    if [[ -n "$cluster_ip" ]]; then
        echo ""
        log_info "ClusterIP Access (from within cluster):"
        echo "  Console: http://$cluster_ip:9001"
        echo "  API: http://$cluster_ip:9000"
        echo "  Service: http://minio.$NAMESPACE.svc.cluster.local:9000"
    fi
    
    # Pod access (for debugging)
    local pod_name=$(kubectl get pod -n "$NAMESPACE" -l app=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$pod_name" ]]; then
        echo ""
        log_info "Debug Access (port-forward):"
        echo "  kubectl port-forward -n $NAMESPACE $pod_name 9000:9000 9001:9001"
        echo "  Then access: http://localhost:9001 (console) or http://localhost:9000 (API)"
    fi
    echo ""
}

# Main function
main() {
    parse_args "$@"
    check_kubectl
    
    log_info "Verifying Minio endpoint health and accessibility"
    log_info "Namespace: $NAMESPACE"
    log_info "Console host: $HOST"
    log_info "API host: $API_HOST"
    echo ""
    
    local errors=0
    
    # Check pod status
    if ! check_pod_status; then
        errors=$((errors + 1))
    fi
    
    # Check service endpoints
    if ! check_service_endpoints; then
        errors=$((errors + 1))
    fi
    
    # Test health endpoints
    if ! test_health_endpoints; then
        errors=$((errors + 1))
    fi
    
    # Check ingress resources
    if [[ "$SKIP_INGRESS" != "true" ]]; then
        if check_ingress; then
            test_ingress_connectivity || errors=$((errors + 1))
        else
            errors=$((errors + 1))
        fi
    fi
    
    # Check LoadBalancer service
    if [[ "$SKIP_LOADBALANCER" != "true" ]]; then
        check_loadbalancer_service || errors=$((errors + 1))
    fi
    
    # Display access information
    display_access_info
    
    # Summary
    echo ""
    if [[ $errors -eq 0 ]]; then
        log_success "All checks passed! Minio is healthy and accessible."
        exit 0
    else
        log_error "Found $errors issue(s). See above for details."
        exit 1
    fi
}

# Run main function
main "$@"
