#!/usr/bin/env bash
###############################################################################
# deploy.sh — apply the AQP minimum infrastructure tier (infra-only).
#
# What this script does:
#   1. preflight.sh — read-only sanity check.
#   2. snapshot.sh capture — pre-deploy state for rollback forensics.
#   3. terraform-bootstrap apply if the state bucket doesn't exist yet.
#   4. Render backend.hcl + terraform.tfvars from the bootstrap outputs +
#      any operator overrides in scripts/deploy.config.
#   5. terraform init + plan on infrastructure/envs/minimum.
#   6. Pause + show plan summary; require ``DEPLOY_CONFIRM=yes`` to apply.
#   7. terraform apply on infrastructure/envs/minimum.
#   8. Write deploy-receipt.json (account id, region, run id, applied SHA).
#
# Does NOT deploy:
#   - The application tier (aqp_platform/terraform/environments/minimum) —
#     run scripts/deploy-app.sh after this once your ECR images are pushed.
#   - The Bedrock model-access enablement (console-only; preflight.sh
#     warns if missing).
#
# Usage:
#   bash scripts/deploy.sh                  # interactive (confirms before apply)
#   DEPLOY_CONFIRM=yes bash scripts/deploy.sh  # non-interactive
#   DEPLOY_DRY_RUN=yes bash scripts/deploy.sh  # plan only, never applies
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${ENV_DIR}/../../.." && pwd)"
BOOTSTRAP_DIR="${REPO_ROOT}/infrastructure/bootstrap"

DEPLOY_DRY_RUN="${DEPLOY_DRY_RUN:-no}"
DEPLOY_CONFIRM="${DEPLOY_CONFIRM:-}"
ACCOUNT_ALIAS="${ACCOUNT_ALIAS:-minimum}"
LOG_FILE="${ENV_DIR}/.deploy.log"
mkdir -p "$(dirname "${LOG_FILE}")"
exec > >(tee -a "${LOG_FILE}") 2>&1

log()   { printf "\033[36m[DEPLOY]\033[0m %s\n" "$*"; }
ok()    { printf "\033[32m  ✓\033[0m %s\n" "$*"; }
fatal() { printf "\033[31m  ✗ FATAL: %s\033[0m\n" "$*"; exit 1; }

trap 'log "deploy.sh exited with code $?"' EXIT

log "deploy.sh starting $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "  dry_run        = ${DEPLOY_DRY_RUN}"
log "  confirm        = ${DEPLOY_CONFIRM:-(prompt)}"
log "  account_alias  = ${ACCOUNT_ALIAS}"

# ---------------------------------------------------------------------------
# Step 1 — preflight
# ---------------------------------------------------------------------------
log "step 1/8 — preflight"
ACCOUNT_ALIAS="${ACCOUNT_ALIAS}" bash "${SCRIPT_DIR}/preflight.sh"

# Resolve identity again for downstream steps.
account_id="$(aws sts get-caller-identity --query Account --output text)"
region="${AWS_REGION:-$(aws configure get region)}"
log "  using account=${account_id} region=${region}"

# ---------------------------------------------------------------------------
# Step 2 — snapshot
# ---------------------------------------------------------------------------
log "step 2/8 — snapshot pre-deploy state"
bash "${SCRIPT_DIR}/snapshot.sh" capture
snap_dir="${ENV_DIR}/.snapshots/latest"
log "  snapshot dir: ${snap_dir}"

# ---------------------------------------------------------------------------
# Step 3 — bootstrap (state bucket + KMS + DynamoDB lock + OIDC) if missing
# ---------------------------------------------------------------------------
bucket_name="aqp-tfstate-${ACCOUNT_ALIAS}"
log "step 3/8 — bootstrap state backend (${bucket_name})"
if aws s3api head-bucket --bucket "${bucket_name}" 2>/dev/null; then
  ok "bootstrap bucket already exists; running ``terraform apply`` to converge"
fi
(
  cd "${BOOTSTRAP_DIR}"
  terraform init -input=false
  terraform plan -input=false -var="account_alias=${ACCOUNT_ALIAS}" -out=tfplan.bootstrap
  if [[ "${DEPLOY_DRY_RUN}" == "yes" ]]; then
    log "  dry run — would terraform apply tfplan.bootstrap here"
  else
    terraform apply -input=false -auto-approve tfplan.bootstrap
  fi
  terraform output -json > "${snap_dir}/bootstrap-outputs.json" 2>/dev/null || true
)
ok "bootstrap apply complete"

# ---------------------------------------------------------------------------
# Step 4 — render backend.hcl + terraform.tfvars
# ---------------------------------------------------------------------------
log "step 4/8 — render backend.hcl + terraform.tfvars"

# Read bootstrap outputs directly from the bootstrap stack's state.
# Bootstrap publishes 5 outputs: kms_key_arn, tfstate_bucket,
# tfstate_lock_legacy_table, github_oidc_provider_arn, account_id.
# We use the SAME KMS key for both tfstate + workload encryption in
# the minimum tier (full multi-account topologies separate them).
(
  cd "${BOOTSTRAP_DIR}"
  if [[ ! -d ".terraform" ]]; then
    terraform init -input=false >/dev/null 2>&1
  fi
)
bootstrap_outputs="$(cd "${BOOTSTRAP_DIR}" && terraform output -json 2>/dev/null || echo '{}')"
kms_arn="$(echo "${bootstrap_outputs}" | jq -r '.kms_key_arn.value // empty')"
github_oidc_arn="$(echo "${bootstrap_outputs}" | jq -r '.github_oidc_provider_arn.value // empty')"
bucket_from_bootstrap="$(echo "${bootstrap_outputs}" | jq -r '.tfstate_bucket.value // empty')"
lock_table="$(echo "${bootstrap_outputs}" | jq -r '.tfstate_lock_legacy_table.value // empty')"

[[ -n "${kms_arn}" ]] || fatal "bootstrap output kms_key_arn missing — bootstrap stack not applied"
[[ -n "${github_oidc_arn}" ]] || fatal "bootstrap output github_oidc_provider_arn missing"
# Prefer the bootstrap's reported bucket name; fall back to convention.
bucket_name="${bucket_from_bootstrap:-${bucket_name}}"
[[ -n "${lock_table}" ]] || lock_table="aqp-tfstate-lock-${ACCOUNT_ALIAS}"

cat > "${ENV_DIR}/backend.hcl" <<EOF
bucket         = "${bucket_name}"
key            = "minimum/main.tfstate"
region         = "${region}"
encrypt        = true
kms_key_id     = "${kms_arn}"
dynamodb_table = "${lock_table}"
use_lockfile   = true
EOF
ok "backend.hcl rendered"

cat > "${ENV_DIR}/terraform.tfvars" <<EOF
account_id               = "${account_id}"
region                   = "${region}"
kms_key_arn              = "${kms_arn}"
github_oidc_provider_arn = "${github_oidc_arn}"
EOF
# assume_role_arn + external_id intentionally omitted — the minimum
# tier uses the caller's session directly (see providers.tf).
ok "terraform.tfvars rendered"

# ---------------------------------------------------------------------------
# Step 5 — terraform init + plan
# ---------------------------------------------------------------------------
log "step 5/8 — terraform init + plan"
(
  cd "${ENV_DIR}"
  terraform init -reconfigure -input=false -backend-config=backend.hcl
  terraform plan -input=false -out=tfplan
  terraform show -no-color tfplan > "${snap_dir}/plan-summary.txt"
  resource_summary="$(grep -E '^Plan:' "${snap_dir}/plan-summary.txt" || echo 'Plan: (no summary line)')"
  echo
  echo "================================ PLAN SUMMARY ================================"
  echo "${resource_summary}"
  echo "Full plan -> ${snap_dir}/plan-summary.txt"
  echo "=============================================================================="
  echo
)

# ---------------------------------------------------------------------------
# Step 6 — confirm before apply
# ---------------------------------------------------------------------------
log "step 6/8 — confirm apply"
if [[ "${DEPLOY_DRY_RUN}" == "yes" ]]; then
  log "  dry run — stopping before apply"
  exit 0
fi
if [[ "${DEPLOY_CONFIRM}" != "yes" ]]; then
  read -r -p "Apply this plan to account ${account_id} region ${region}? [yes/NO] " answer
  case "${answer}" in
    yes|YES|y|Y) ok "confirmed";;
    *) log "aborted by operator"; exit 0;;
  esac
fi

# ---------------------------------------------------------------------------
# Step 7 — terraform apply
# ---------------------------------------------------------------------------
log "step 7/8 — terraform apply"
(
  cd "${ENV_DIR}"
  terraform apply -input=false tfplan
)
ok "apply complete"

# ---------------------------------------------------------------------------
# Step 8 — deploy receipt
# ---------------------------------------------------------------------------
log "step 8/8 — write deploy receipt"
applied_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
git_sha="$(cd "${REPO_ROOT}" && git rev-parse HEAD 2>/dev/null || echo "no-git")"
cat > "${snap_dir}/deploy-receipt.json" <<EOF
{
  "deployed_at":   "${applied_at}",
  "account_id":    "${account_id}",
  "region":        "${region}",
  "snapshot_dir":  "${snap_dir}",
  "git_sha":       "${git_sha}",
  "env_dir":       "${ENV_DIR}",
  "rollback":      "bash $(realpath --relative-to="${REPO_ROOT}" "${SCRIPT_DIR}/destroy.sh")"
}
EOF
ok "receipt -> ${snap_dir}/deploy-receipt.json"

log "deploy.sh complete — rollback with: bash ${SCRIPT_DIR}/destroy.sh"
