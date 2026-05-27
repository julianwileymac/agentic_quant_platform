#!/usr/bin/env bash
# =============================================================================
# Grant tenant-wide admin consent for the AQP staff Entra apps.
#
# Workstream "Entra internal tenant" — after Terraform creates the
# aqp-staff app registration with its required Microsoft Graph
# permissions, those permissions are *requested* but not yet
# *consented*. This script wraps the Azure CLI ``az ad app
# permission admin-consent`` call so the operator doesn't have to
# remember the exact incantation.
#
# Required tools: ``az`` (Azure CLI) signed in as a global admin or
# Privileged Role Administrator. The CLI itself enforces the role
# check; we only wrap the boilerplate.
#
# Usage:
#   scripts/identity/grant_admin_consent.sh <staff_app_client_id>
#
# Where to find the client id:
#   * Terraform output ``entra_staff_app_client_id``, OR
#   * scripts/identity/list_entra_app_role_assignments.py --apps
# =============================================================================
set -euo pipefail

if (( $# != 1 )); then
  cat >&2 <<EOT
usage: $(basename "$0") <staff_app_client_id>

Grants tenant-wide admin consent for the AQP staff app's required
Microsoft Graph permissions (User.Read, Group.Read.All, etc.).

Example:
  $(basename "$0") "00000000-1111-2222-3333-444444444444"
EOT
  exit 1
fi

CLIENT_ID="$1"

if [[ ! "${CLIENT_ID}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
  echo "error: ${CLIENT_ID} doesn't look like a UUID" >&2
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  echo "error: az (Azure CLI) is not on PATH" >&2
  echo "  install: https://learn.microsoft.com/cli/azure/install-azure-cli" >&2
  exit 1
fi

# Confirm we're signed in.
if ! az account show >/dev/null 2>&1; then
  echo "error: ``az`` is not logged in. Run ``az login`` first." >&2
  exit 1
fi

ACTIVE_TENANT="$(az account show --query tenantId -o tsv)"
echo "==> Granting admin consent for app ${CLIENT_ID} on tenant ${ACTIVE_TENANT}"

az ad app permission admin-consent --id "${CLIENT_ID}"

echo
echo "==> Verifying delegated grants"
az ad app permission list-grants --id "${CLIENT_ID}" -o table

echo
echo "Done. The staff app's Microsoft Graph permissions are now consented."
echo "Operators can verify with: scripts/identity/verify_entra_login.py"
