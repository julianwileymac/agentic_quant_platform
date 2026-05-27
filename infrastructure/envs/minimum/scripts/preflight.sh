#!/usr/bin/env bash
###############################################################################
# preflight.sh — read-only validation before any terraform apply.
#
# Confirms:
#   1. aws CLI is present + credentials are configured + we can reach STS.
#   2. terraform CLI is present + at the pinned 1.10.x line.
#   3. jq + bash >= 4 are present (for the helper scripts).
#   4. The active region honours the SCP allowlist (us-east-1 / us-east-2 / us-west-2).
#   5. The connected account is the one the operator INTENDS — surfaces both
#      the account id + alias so a fat-fingered profile doesn't deploy to prod.
#   6. The bootstrap state bucket either exists OR we can create it (no
#      pre-existing bucket owned by another account squatting on the name).
#   7. The Bedrock model access for Claude Haiku 4.5 has been requested
#      (if API call fails, prints the console URL to enable it manually).
#
# Read-only — zero billable resources are created. Run this BEFORE every
# deploy.sh invocation. Exits 0 on green light, non-zero with a clear
# remediation hint on each gate.
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${LOG_FILE:-${ENV_DIR}/.preflight.log}"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
mkdir -p "$(dirname "${LOG_FILE}")"
exec > >(tee -a "${LOG_FILE}") 2>&1

log()  { printf "\033[36m[PREFLIGHT]\033[0m %s\n" "$*"; }
ok()   { printf "\033[32m  ✓\033[0m %s\n" "$*"; }
warn() { printf "\033[33m  ⚠\033[0m %s\n" "$*"; }
fail() { printf "\033[31m  ✗ %s\033[0m\n" "$*"; exit 1; }

log "preflight starting $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# Gate 1 — required CLIs
# ---------------------------------------------------------------------------
log "checking required CLIs"
command -v aws       >/dev/null 2>&1 || fail "aws CLI not on PATH. Install: https://aws.amazon.com/cli/"
command -v terraform >/dev/null 2>&1 || fail "terraform not on PATH. Install: https://developer.hashicorp.com/terraform/install"
command -v jq        >/dev/null 2>&1 || fail "jq not on PATH. Install: https://stedolan.github.io/jq/"
ok "aws / terraform / jq present"

tf_version="$(terraform version -json | jq -r '.terraform_version')"
case "${tf_version}" in
  1.10.*) ok "terraform ${tf_version} (matches 1.10.x pin)";;
  *)      warn "terraform ${tf_version} — workflow pins 1.10.0; local deploy may drift";;
esac

# ---------------------------------------------------------------------------
# Gate 2 — AWS identity
# ---------------------------------------------------------------------------
log "checking AWS connectivity"
caller_json="$(aws sts get-caller-identity --output json 2>/dev/null || true)"
[[ -n "${caller_json}" ]] || fail "aws sts get-caller-identity returned nothing — credentials not configured. Set AWS_PROFILE or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY."

account_id="$(echo "${caller_json}" | jq -r '.Account')"
arn="$(echo "${caller_json}" | jq -r '.Arn')"
ok "AWS account ${account_id}"
ok "principal: ${arn}"

# Account alias (best-effort, may 403 for non-admin identities).
alias_json="$(aws iam list-account-aliases --output json 2>/dev/null || true)"
if [[ -n "${alias_json}" ]]; then
  account_alias="$(echo "${alias_json}" | jq -r '.AccountAliases[0] // "(no alias)"')"
  ok "account alias: ${account_alias}"
fi

# ---------------------------------------------------------------------------
# Gate 3 — region allowlist
# ---------------------------------------------------------------------------
log "checking active region"
region="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo "")}"
[[ -n "${region}" ]] || fail "no region configured. Set AWS_REGION=us-east-1 (or us-east-2 / us-west-2)."
case "${region}" in
  us-east-1|us-east-2|us-west-2)
    ok "region ${region} (SCP allowlist OK)";;
  *)
    fail "region ${region} is outside the SCP allowlist (us-east-1 / us-east-2 / us-west-2). Set AWS_REGION before re-running.";;
esac

# ---------------------------------------------------------------------------
# Gate 4 — bootstrap state bucket squat check
# ---------------------------------------------------------------------------
# Bootstrap names the bucket ``aqp-tfstate-${account_alias}`` where
# ``account_alias`` is operator-supplied (defaults to ``minimum`` for
# this tier). Override with ``ACCOUNT_ALIAS=<alias>`` before running.
account_alias="${ACCOUNT_ALIAS:-minimum}"
log "checking bootstrap state bucket name availability (alias=${account_alias})"
bucket_name="aqp-tfstate-${account_alias}"
bucket_check="$(aws s3api head-bucket --bucket "${bucket_name}" 2>&1 || true)"
case "${bucket_check}" in
  *"404"*|*"Not Found"*|"")
    ok "bucket ${bucket_name} is free for bootstrap to create";;
  *"403"*|*"Forbidden"*)
    fail "bucket ${bucket_name} exists in another account — pick a different ACCOUNT_ALIAS or release the name.";;
  *)
    owner="$(aws s3api get-bucket-acl --bucket "${bucket_name}" --output json 2>/dev/null | jq -r '.Owner.ID' || echo "?")"
    ok "bucket ${bucket_name} already exists (owner=${owner:0:12}…) — bootstrap will be a no-op apply";;
esac

# ---------------------------------------------------------------------------
# Gate 5 — Bedrock model access for Claude Haiku 4.5
# ---------------------------------------------------------------------------
log "checking Bedrock model access for anthropic.claude-haiku-4-5"
model_check="$(aws bedrock get-foundation-model \
  --model-identifier anthropic.claude-haiku-4-5-20251022-v1:0 \
  --output json 2>&1 || true)"
if echo "${model_check}" | jq -e '.modelDetails' >/dev/null 2>&1; then
  ok "Claude Haiku 4.5 reachable in ${region}"
elif echo "${model_check}" | grep -qi "AccessDenied\|not.*entitled\|not.*authorized"; then
  warn "Bedrock model access NOT granted for Claude Haiku 4.5 in ${region}."
  warn "Enable manually: https://${region}.console.aws.amazon.com/bedrock/home?region=${region}#/modelaccess"
  warn "The deploy will succeed but Bedrock invocations will return AccessDeniedException until enabled."
else
  warn "could not verify Bedrock model access: ${model_check}"
fi

# ---------------------------------------------------------------------------
# Gate 6 — no in-flight terraform on this env (state lock check)
# ---------------------------------------------------------------------------
log "checking for in-flight terraform runs"
lock_table="aqp-tfstate-lock-${account_alias}"
lock_check="$(aws dynamodb scan --table-name "${lock_table}" --max-items 5 --output json 2>&1 || true)"
if echo "${lock_check}" | jq -e '.Items[0]' >/dev/null 2>&1; then
  active_locks="$(echo "${lock_check}" | jq -r '.Items[] | .LockID.S')"
  warn "active terraform locks detected in ${lock_table}:"
  echo "${active_locks}" | sed 's/^/    /'
  warn "if these are stale, ``terraform force-unlock <ID>`` clears them."
elif echo "${lock_check}" | grep -qi "ResourceNotFoundException"; then
  ok "lock table not yet created — bootstrap will create ${lock_table}"
else
  ok "no in-flight terraform locks"
fi

log "preflight green — safe to run deploy.sh"
