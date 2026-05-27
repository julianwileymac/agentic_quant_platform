#!/usr/bin/env bash
###############################################################################
# snapshot.sh — capture pre-deploy state so rollback is forensic-grade.
#
# Captures BEFORE any terraform action:
#   1. AWS account id + region + caller identity (proof of who deployed).
#   2. Existing resources tagged ``managed_by=terraform env=minimum`` —
#      these are the rollback target set; anything else is pre-existing
#      and MUST NOT be touched by destroy.sh.
#   3. The current ``backend.hcl`` + ``terraform.tfvars`` (so a future
#      operator can replay the exact deploy).
#   4. SHA-256 of every .tf file in this env (for tamper detection).
#   5. The bootstrap state bucket name + the dynamodb lock table id.
#
# Outputs to ``.snapshots/<UTC-timestamp>/`` so multiple deploys retain
# their pre-state independently. Re-run ``snapshot.sh capture`` before
# each deploy; ``snapshot.sh list`` to view past snapshots.
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SNAP_ROOT="${ENV_DIR}/.snapshots"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SNAP_DIR="${SNAP_ROOT}/${TS}"

ACTION="${1:-capture}"

case "${ACTION}" in
  list)
    if [[ -d "${SNAP_ROOT}" ]]; then
      ls -1 "${SNAP_ROOT}" | sort -r
    else
      echo "no snapshots yet"
    fi
    exit 0
    ;;
  capture)
    : # fall through
    ;;
  *)
    echo "usage: $(basename "$0") [capture|list]"
    exit 2
    ;;
esac

mkdir -p "${SNAP_DIR}"
exec > >(tee -a "${SNAP_DIR}/snapshot.log") 2>&1

echo "[SNAPSHOT] capturing pre-deploy state to ${SNAP_DIR}"

# 1. Caller identity
aws sts get-caller-identity --output json > "${SNAP_DIR}/caller-identity.json"
account_id="$(jq -r '.Account' < "${SNAP_DIR}/caller-identity.json")"
region="${AWS_REGION:-$(aws configure get region)}"
echo "${region}" > "${SNAP_DIR}/region.txt"

# 2. Pre-existing tagged resources — the rollback safety net.
# resourcegroupstaggingapi sees every taggable resource in the region.
aws resourcegroupstaggingapi get-resources \
  --tag-filters "Key=managed_by,Values=terraform" "Key=env,Values=minimum" \
  --resources-per-page 100 \
  --output json > "${SNAP_DIR}/preexisting-tagged-resources.json" 2>/dev/null || \
  echo "{}" > "${SNAP_DIR}/preexisting-tagged-resources.json"

preexisting_count="$(jq -r '.ResourceTagMappingList | length' < "${SNAP_DIR}/preexisting-tagged-resources.json")"
echo "[SNAPSHOT] preexisting env=minimum resources: ${preexisting_count}"

# 3. Snapshot the inputs that drive the apply.
for f in backend.hcl terraform.tfvars; do
  if [[ -f "${ENV_DIR}/${f}" ]]; then
    cp "${ENV_DIR}/${f}" "${SNAP_DIR}/${f}"
  fi
done

# 4. SHA-256 of every .tf file under this env.
find "${ENV_DIR}" -maxdepth 2 -name '*.tf' -type f -print0 \
  | xargs -0 sha256sum > "${SNAP_DIR}/tf-checksums.txt" 2>/dev/null || true

# 5. Bootstrap handles.
{
  echo "bucket=aqp-tfstate-${account_id}"
  echo "lock_table=aqp-tflock-${account_id}"
  echo "region=${region}"
  echo "account_id=${account_id}"
} > "${SNAP_DIR}/bootstrap-handles.env"

# 6. Bootstrap state (if exists) — copy a versioned object out of the
#    state bucket so destroy.sh can replay the previous-good state.
bucket="aqp-tfstate-${account_id}"
if aws s3api head-bucket --bucket "${bucket}" 2>/dev/null; then
  mkdir -p "${SNAP_DIR}/tfstate"
  for key in \
      "minimum/main.tfstate" \
      "aqp_platform/minimum/terraform.tfstate"; do
    if aws s3 cp "s3://${bucket}/${key}" "${SNAP_DIR}/tfstate/$(basename "${key}")" 2>/dev/null; then
      echo "[SNAPSHOT] preserved ${key}"
    fi
  done
fi

echo "[SNAPSHOT] captured -> ${SNAP_DIR}"
ln -sfn "${TS}" "${SNAP_ROOT}/latest"
echo "[SNAPSHOT] symlink ${SNAP_ROOT}/latest -> ${TS}"
