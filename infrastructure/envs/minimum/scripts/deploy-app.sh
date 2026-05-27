#!/usr/bin/env bash
###############################################################################
# deploy-app.sh — apply the AQP minimum application tier (Cognito+ALB+Fargate).
#
# Run AFTER scripts/deploy.sh (which provisions the infrastructure tier)
# AND after you've pushed an aqp-admin image to ECR (via build-publish.yml
# or a manual ``docker buildx``).
#
# What this script does:
#   1. Confirms scripts/deploy.sh has been run (snapshot + receipt exist).
#   2. Walks the operator through the two extra inputs the app tier needs:
#        - ACM certificate ARN (regional, for the ALB HTTPS listener).
#        - aqp-admin image tag in ECR.
#   3. Renders backend.hcl + terraform.tfvars in the app-tier env dir.
#   4. terraform init + plan + apply.
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${ENV_DIR}/../../.." && pwd)"
APP_ENV_DIR="${REPO_ROOT}/aqp_platform/terraform/environments/minimum"

DEPLOY_CONFIRM="${DEPLOY_CONFIRM:-}"
DEPLOY_DRY_RUN="${DEPLOY_DRY_RUN:-no}"
ACM_CERT_ARN="${ACM_CERT_ARN:-}"
ADMIN_IMAGE_TAG="${ADMIN_IMAGE_TAG:-}"

LOG_FILE="${APP_ENV_DIR}/.deploy-app.log"
mkdir -p "$(dirname "${LOG_FILE}")"
exec > >(tee -a "${LOG_FILE}") 2>&1

log()   { printf "\033[36m[DEPLOY-APP]\033[0m %s\n" "$*"; }
ok()    { printf "\033[32m  ✓\033[0m %s\n" "$*"; }
fatal() { printf "\033[31m  ✗ FATAL: %s\033[0m\n" "$*"; exit 1; }

trap 'log "deploy-app.sh exited with code $?"' EXIT

# Sanity: scripts/deploy.sh has been run.
if [[ ! -f "${ENV_DIR}/.snapshots/latest/deploy-receipt.json" ]]; then
  fatal "no infrastructure-tier deploy receipt — run scripts/deploy.sh first"
fi
account_id="$(jq -r '.account_id' < "${ENV_DIR}/.snapshots/latest/deploy-receipt.json")"
region="$(jq -r '.region' < "${ENV_DIR}/.snapshots/latest/deploy-receipt.json")"
log "infra tier deployed to account=${account_id} region=${region}"

# Confirm caller matches the infra deploy.
caller_account="$(aws sts get-caller-identity --query Account --output text)"
[[ "${caller_account}" == "${account_id}" ]] || \
  fatal "caller account ${caller_account} != infra account ${account_id}"

# Collect ACM cert ARN.
if [[ -z "${ACM_CERT_ARN}" ]]; then
  log "no ACM_CERT_ARN env var; listing regional certs in ${region}:"
  aws acm list-certificates --region "${region}" --output table || true
  read -r -p "Paste ACM cert ARN (regional; us-east-1 ALB needs us-east-1 cert): " ACM_CERT_ARN
fi
[[ "${ACM_CERT_ARN}" == arn:aws:acm:* ]] || fatal "invalid ACM cert ARN: ${ACM_CERT_ARN}"

# Collect image tag.
if [[ -z "${ADMIN_IMAGE_TAG}" ]]; then
  log "no ADMIN_IMAGE_TAG env var; listing aqp-admin tags:"
  aws ecr describe-images --repository-name aqp-admin --region "${region}" \
    --query 'imageDetails[].imageTags[]' --output table 2>/dev/null || \
    fatal "no aqp-admin ECR repo — run build-publish.yml first"
  read -r -p "Image tag to deploy: " ADMIN_IMAGE_TAG
fi

# Read bootstrap outputs from the bootstrap stack's state. Mirrors
# deploy.sh — same KMS + DynamoDB handles.
BOOTSTRAP_DIR="${REPO_ROOT}/infrastructure/bootstrap"
(
  cd "${BOOTSTRAP_DIR}"
  if [[ ! -d ".terraform" ]]; then
    terraform init -input=false >/dev/null 2>&1
  fi
)
bootstrap_outputs="$(cd "${BOOTSTRAP_DIR}" && terraform output -json 2>/dev/null || echo '{}')"
kms_arn="$(echo "${bootstrap_outputs}" | jq -r '.kms_key_arn.value // empty')"
lock_table="$(echo "${bootstrap_outputs}" | jq -r '.tfstate_lock_legacy_table.value // empty')"
[[ -n "${kms_arn}" ]] || fatal "bootstrap output kms_key_arn missing"
[[ -n "${lock_table}" ]] || lock_table="aqp-tflock-${account_id}"

bucket_from_bootstrap="$(echo "${bootstrap_outputs}" | jq -r '.tfstate_bucket.value // empty')"
[[ -n "${bucket_from_bootstrap}" ]] || fatal "bootstrap output tfstate_bucket missing"

cat > "${APP_ENV_DIR}/backend.hcl" <<EOF
bucket         = "${bucket_from_bootstrap}"
key            = "aqp_platform/minimum/terraform.tfstate"
region         = "${region}"
encrypt        = true
kms_key_id     = "${kms_arn}"
dynamodb_table = "${lock_table}"
use_lockfile   = true
EOF

cat > "${APP_ENV_DIR}/terraform.tfvars" <<EOF
account_id              = "${account_id}"
region                  = "${region}"
acm_certificate_arn_alb = "${ACM_CERT_ARN}"
admin_image_tag         = "${ADMIN_IMAGE_TAG}"
EOF
# assume_role_arn + external_id intentionally omitted — minimum tier
# uses the caller's session directly.
ok "backend.hcl + terraform.tfvars rendered"

(
  cd "${APP_ENV_DIR}"
  terraform init -reconfigure -input=false -backend-config=backend.hcl
  terraform plan -input=false -out=tfplan
  terraform show -no-color tfplan | grep -E '^Plan:' || true

  if [[ "${DEPLOY_DRY_RUN}" == "yes" ]]; then
    log "dry run — stopping before apply"
    exit 0
  fi
  if [[ "${DEPLOY_CONFIRM}" != "yes" ]]; then
    read -r -p "Apply this app-tier plan? [yes/NO] " answer
    case "${answer}" in
      yes|YES|y|Y) ;;
      *) log "aborted"; exit 0;;
    esac
  fi
  terraform apply -input=false tfplan
)

alb_dns="$(cd "${APP_ENV_DIR}" && terraform output -raw alb_dns_name 2>/dev/null || echo "")"
ok "app tier deployed"
[[ -n "${alb_dns}" ]] && ok "ALB DNS: ${alb_dns}"
log "smoke test: curl -sSI https://${alb_dns}/healthz"
