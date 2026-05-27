#!/usr/bin/env bash
# =============================================================================
# Plan-only preview for the aqp_entra_directory Terraform module.
#
# Workstream "Entra internal tenant" — runs ``terraform init -backend=false``
# + ``terraform validate`` + ``terraform plan`` against the wiley-tech
# environment WITHOUT ever calling apply. Operators run this locally
# (or PR CI runs it via .github/workflows/entra-terraform.yml).
#
# AGENTS rule 42: never call ``terraform apply`` directly. The apply
# helper lives at scripts/identity/entra_terraform_apply_via_runtime.py
# and routes through TerraformRuntime so the run lands a
# ``terraform_runs`` audit row.
#
# Required env (sourced from Vault by the operator before running):
#   AZURE_TENANT_ID            Entra tenant under management
#   AZURE_CLIENT_ID            Service principal id with the IAM noted
#                              in modules/aqp_entra_directory/README.md
#   AZURE_CLIENT_SECRET        SP secret OR (preferred)
#   AZURE_OIDC_TOKEN           Federated OIDC token from CI
#   TF_VAR_entra_tenant_id     Same value as AZURE_TENANT_ID
#   TF_VAR_entra_enabled       "true" to flip the module on; default false
#
# Usage:
#   scripts/identity/entra_terraform_plan.sh [--target wiley-tech]
# =============================================================================
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TARGET="${1:-wiley-tech}"
ENV_DIR="${REPO_ROOT}/aqp_platform/terraform/environments/${TARGET}"
MOD_DIR="${REPO_ROOT}/aqp_platform/terraform/modules/aqp_entra_directory"

if [[ ! -d "${ENV_DIR}" ]]; then
  echo "error: environment ${TARGET} not found at ${ENV_DIR}" >&2
  exit 1
fi

# Friendly check for required env vars; the actual provider auth happens
# inside terraform.
missing=()
for var in AZURE_TENANT_ID; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("${var}")
  fi
done
if [[ -z "${AZURE_CLIENT_SECRET:-}" && -z "${AZURE_OIDC_TOKEN:-}" && -z "${ARM_USE_CLI:-}" ]]; then
  missing+=("AZURE_CLIENT_SECRET or AZURE_OIDC_TOKEN or ARM_USE_CLI=true")
fi
if (( ${#missing[@]} > 0 )); then
  echo "error: missing required env: ${missing[*]}" >&2
  echo "       see scripts/identity/entra_terraform_plan.sh header for details" >&2
  exit 1
fi

# Derive the matching TF_VAR from the AZURE_* env so operators don't have
# to set both.
export TF_VAR_entra_tenant_id="${TF_VAR_entra_tenant_id:-${AZURE_TENANT_ID}}"
export TF_VAR_entra_enabled="${TF_VAR_entra_enabled:-true}"

echo "==> Module-level fmt + validate (${MOD_DIR})"
terraform -chdir="${MOD_DIR}" fmt -check -recursive
terraform -chdir="${MOD_DIR}" init -backend=false -upgrade
terraform -chdir="${MOD_DIR}" validate

echo
echo "==> Environment-level plan (${ENV_DIR})"
terraform -chdir="${ENV_DIR}" init -backend=false -upgrade

# Constrain the plan to the new module + its outputs so a parent-module
# drift doesn't poison the preview.
terraform -chdir="${ENV_DIR}" plan \
  -target=module.aqp_entra_directory \
  -out=/tmp/aqp-entra-${TARGET}.plan

echo
echo "==> Plan written to /tmp/aqp-entra-${TARGET}.plan"
echo "    Inspect with: terraform -chdir=\"${ENV_DIR}\" show /tmp/aqp-entra-${TARGET}.plan"
echo
echo "Apply path: scripts/identity/entra_terraform_apply_via_runtime.py --target ${TARGET}"
