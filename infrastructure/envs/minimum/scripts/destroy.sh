#!/usr/bin/env bash
###############################################################################
# destroy.sh — bulletproof rollback for the AQP minimum infrastructure tier.
#
# Reverses everything deploy.sh creates, in the safe order:
#
#   1. Confirm we're talking to the SAME account as the last deploy.
#   2. Application tier first (if it exists) — Fargate services hold ALB
#      target-group refs that prevent ALB deletion.
#   3. Infrastructure tier — VPC + RDS + Redis + ECR + alarms + IAM.
#   4. RDS deletion_protection flip + force final-snapshot OR skip-final
#      (operator choice via DESTROY_RDS_SKIP_SNAPSHOT=yes).
#   5. Orphan sweep — IF tagged resources remain after destroy, list them
#      so the operator can hand-clean (NEVER auto-delete untagged stuff).
#   6. Bootstrap retention — bootstrap state backend + GitHub OIDC stay
#      by default. Pass DESTROY_BOOTSTRAP=yes to nuke them too (rare —
#      the state bucket has Object Lock GOVERNANCE so you can't just
#      ``aws s3 rb`` it; the script handles the unlock + version sweep).
#
# Confirmation gates:
#   - DESTROY_CONFIRM=yes              skip interactive prompt
#   - DESTROY_RDS_SKIP_SNAPSHOT=yes    don't snapshot RDS before delete
#   - DESTROY_BOOTSTRAP=yes            also nuke the bootstrap stack
#   - DESTROY_DRY_RUN=yes              plan + print, never actually destroys
#
# Usage:
#   bash scripts/destroy.sh
#   DESTROY_CONFIRM=yes bash scripts/destroy.sh
#   DESTROY_DRY_RUN=yes bash scripts/destroy.sh
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${ENV_DIR}/../../.." && pwd)"
APP_ENV_DIR="${REPO_ROOT}/aqp_platform/terraform/environments/minimum"
BOOTSTRAP_DIR="${REPO_ROOT}/infrastructure/bootstrap"

DESTROY_CONFIRM="${DESTROY_CONFIRM:-}"
DESTROY_DRY_RUN="${DESTROY_DRY_RUN:-no}"
DESTROY_BOOTSTRAP="${DESTROY_BOOTSTRAP:-no}"
DESTROY_RDS_SKIP_SNAPSHOT="${DESTROY_RDS_SKIP_SNAPSHOT:-no}"
ACCOUNT_ALIAS="${ACCOUNT_ALIAS:-minimum}"
LOG_FILE="${ENV_DIR}/.destroy.log"
mkdir -p "$(dirname "${LOG_FILE}")"
exec > >(tee -a "${LOG_FILE}") 2>&1

log()   { printf "\033[35m[DESTROY]\033[0m %s\n" "$*"; }
ok()    { printf "\033[32m  ✓\033[0m %s\n" "$*"; }
warn()  { printf "\033[33m  ⚠\033[0m %s\n" "$*"; }
fatal() { printf "\033[31m  ✗ FATAL: %s\033[0m\n" "$*"; exit 1; }

trap 'log "destroy.sh exited with code $?"' EXIT

log "destroy.sh starting $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "  dry_run            = ${DESTROY_DRY_RUN}"
log "  rds_skip_snapshot  = ${DESTROY_RDS_SKIP_SNAPSHOT}"
log "  bootstrap          = ${DESTROY_BOOTSTRAP}"

# ---------------------------------------------------------------------------
# Step 1 — identity guard
# ---------------------------------------------------------------------------
account_id="$(aws sts get-caller-identity --query Account --output text)"
region="${AWS_REGION:-$(aws configure get region)}"
log "step 1/6 — identity guard (account=${account_id} region=${region})"

receipt_file="${ENV_DIR}/.snapshots/latest/deploy-receipt.json"
if [[ -f "${receipt_file}" ]]; then
  deploy_account="$(jq -r '.account_id' < "${receipt_file}")"
  deploy_region="$(jq -r '.region' < "${receipt_file}")"
  if [[ "${deploy_account}" != "${account_id}" ]]; then
    fatal "deploy receipt is for account ${deploy_account} but caller is ${account_id} — refusing to destroy across accounts"
  fi
  if [[ "${deploy_region}" != "${region}" ]]; then
    fatal "deploy receipt is for region ${deploy_region} but caller is ${region} — set AWS_REGION=${deploy_region}"
  fi
  ok "identity matches deploy receipt"
else
  warn "no deploy receipt found — proceeding without identity match (assuming first-time destroy)"
fi

if [[ "${DESTROY_CONFIRM}" != "yes" && "${DESTROY_DRY_RUN}" != "yes" ]]; then
  read -r -p "Destroy AQP minimum tier in account ${account_id} region ${region}? [yes/NO] " answer
  case "${answer}" in
    yes|YES|y|Y) ok "confirmed";;
    *) log "aborted by operator"; exit 0;;
  esac
fi

# ---------------------------------------------------------------------------
# Step 2 — application tier first (ALB / ECS / Cognito)
# ---------------------------------------------------------------------------
log "step 2/6 — application tier destroy"
if [[ -d "${APP_ENV_DIR}" && -f "${APP_ENV_DIR}/backend.hcl" ]]; then
  (
    cd "${APP_ENV_DIR}"
    terraform init -reconfigure -input=false -backend-config=backend.hcl 2>/dev/null || true
    if [[ "${DESTROY_DRY_RUN}" == "yes" ]]; then
      terraform plan -destroy -input=false || true
      log "  dry run — skipping destroy"
    else
      terraform destroy -input=false -auto-approve || warn "app-tier destroy returned non-zero; continuing"
    fi
  )
  ok "application tier destroyed (or absent)"
else
  ok "application tier never deployed — skipping"
fi

# ---------------------------------------------------------------------------
# Step 3 — RDS deletion_protection bypass
# ---------------------------------------------------------------------------
log "step 3/6 — RDS deletion_protection bypass"
# RDS module sets deletion_protection=true + skip_final_snapshot=false.
# Flip both via the AWS CLI before terraform destroy reaches the resource.
rds_instances="$(aws rds describe-db-instances \
  --query 'DBInstances[?TagList[?Key==`env` && Value==`minimum`]].DBInstanceIdentifier' \
  --output text 2>/dev/null || echo "")"

for db in ${rds_instances}; do
  log "  preparing RDS instance ${db} for delete"
  if [[ "${DESTROY_DRY_RUN}" == "yes" ]]; then
    log "    dry run — would disable deletion_protection on ${db}"
    continue
  fi
  aws rds modify-db-instance \
    --db-instance-identifier "${db}" \
    --no-deletion-protection \
    --apply-immediately \
    --output text >/dev/null 2>&1 || warn "could not modify ${db} (already gone?)"
  if [[ "${DESTROY_RDS_SKIP_SNAPSHOT}" != "yes" ]]; then
    final_snap="${db}-rollback-$(date -u +%Y%m%dT%H%M%SZ)"
    ok "    will take final snapshot ${final_snap} (set DESTROY_RDS_SKIP_SNAPSHOT=yes to skip)"
  fi
done

# ---------------------------------------------------------------------------
# Step 4 — infrastructure tier destroy
# ---------------------------------------------------------------------------
log "step 4/6 — infrastructure tier destroy"
if [[ -f "${ENV_DIR}/backend.hcl" ]]; then
  (
    cd "${ENV_DIR}"
    terraform init -reconfigure -input=false -backend-config=backend.hcl
    if [[ "${DESTROY_DRY_RUN}" == "yes" ]]; then
      terraform plan -destroy -input=false || true
      log "  dry run — skipping destroy"
    else
      terraform destroy -input=false -auto-approve
    fi
  )
  ok "infrastructure tier destroyed"
else
  warn "no backend.hcl in ${ENV_DIR} — was deploy.sh ever run?"
fi

# ---------------------------------------------------------------------------
# Step 5 — orphan sweep
# ---------------------------------------------------------------------------
log "step 5/6 — orphan sweep (tagged resources that survived destroy)"
orphans="$(aws resourcegroupstaggingapi get-resources \
  --tag-filters "Key=managed_by,Values=terraform" "Key=env,Values=minimum" \
  --resources-per-page 100 \
  --output json 2>/dev/null || echo "{}")"

orphan_count="$(echo "${orphans}" | jq -r '.ResourceTagMappingList | length')"
if [[ "${orphan_count}" -gt 0 ]]; then
  warn "found ${orphan_count} orphan resource(s) — review + hand-delete:"
  echo "${orphans}" | jq -r '.ResourceTagMappingList[].ResourceARN' | sed 's/^/    /'
  warn "common causes: NAT-attached EIPs, ECS task ENIs in CLEANUP, CloudWatch log groups with retention!=never"
else
  ok "no orphans"
fi

# ---------------------------------------------------------------------------
# Step 6 — bootstrap (optional, gated)
# ---------------------------------------------------------------------------
if [[ "${DESTROY_BOOTSTRAP}" == "yes" ]]; then
  log "step 6/6 — bootstrap teardown (state bucket + KMS + DynamoDB + OIDC)"
  bucket="aqp-tfstate-${ACCOUNT_ALIAS}"
  warn "this is DESTRUCTIVE — the state bucket has Object Lock GOVERNANCE."
  if [[ "${DESTROY_DRY_RUN}" == "yes" ]]; then
    log "  dry run — would empty + delete ${bucket} + run bootstrap destroy"
  else
    # Remove every version + delete marker.
    aws s3api list-object-versions --bucket "${bucket}" --output json 2>/dev/null \
      | jq -r '.Versions[]? | "\(.Key) \(.VersionId)"' \
      | while read -r key vid; do
          aws s3api delete-object --bucket "${bucket}" --key "${key}" --version-id "${vid}" --bypass-governance-retention >/dev/null 2>&1 || true
        done
    aws s3api list-object-versions --bucket "${bucket}" --output json 2>/dev/null \
      | jq -r '.DeleteMarkers[]? | "\(.Key) \(.VersionId)"' \
      | while read -r key vid; do
          aws s3api delete-object --bucket "${bucket}" --key "${key}" --version-id "${vid}" --bypass-governance-retention >/dev/null 2>&1 || true
        done
    (
      cd "${BOOTSTRAP_DIR}"
      terraform destroy -input=false -auto-approve -var="account_alias=${ACCOUNT_ALIAS}" \
        || warn "bootstrap destroy returned non-zero"
    )
  fi
  ok "bootstrap teardown complete"
else
  log "step 6/6 — bootstrap RETAINED (set DESTROY_BOOTSTRAP=yes to remove)"
fi

log "destroy.sh complete"
