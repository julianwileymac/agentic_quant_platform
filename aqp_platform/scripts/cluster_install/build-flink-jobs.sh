#!/usr/bin/env bash
# =============================================================================
# Build + publish the flink-trading (PyFlink) image and upload jobs to MinIO.
# =============================================================================
# For the Java TA-Lib job bundle, use
# ``bootstrap/scripts/build-flink-jobs-java.sh`` instead (separate image +
# per-category shadow JARs uploaded to ``s3://flink-jobs/java/``).
#
# Prerequisites:
#   * Docker Buildx with a multi-arch builder configured
#     (``docker buildx create --name aqp --use`` once).
#   * ``mc`` (MinIO client) configured with an ``aqp`` alias pointed at the
#     in-cluster MinIO, e.g. via port-forward:
#       kubectl port-forward -n aqp-data-services svc/minio 9000:9000 &
#       mc alias set aqp http://localhost:9000 minioadmin minioadmin123
#
# Usage:
#   bash bootstrap/scripts/build-flink-jobs.sh \
#     --image ghcr.io/julianwiley/flink-trading:1.20 \
#     [--push] \
#     [--skip-jobs]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
JOBS_DIR="${REPO_ROOT}/flink-jobs"

IMAGE="ghcr.io/julianwiley/flink-trading:1.20"
PUSH=0
SKIP_JOBS=0
MC_ALIAS="aqp"
MC_JOBS_BUCKET="aqp/flink-jobs"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --image)
            IMAGE="$2"; shift 2 ;;
        --push)
            PUSH=1; shift ;;
        --skip-jobs)
            SKIP_JOBS=1; shift ;;
        --mc-alias)
            MC_ALIAS="$2"; shift 2 ;;
        --mc-bucket)
            MC_JOBS_BUCKET="$2"; shift 2 ;;
        *)
            echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

echo "[build-flink-jobs] image=${IMAGE} push=${PUSH} skip-jobs=${SKIP_JOBS}"

# Sync schemas from aqp (ensures the Flink image ships the same contract).
AQP_SCHEMAS="${REPO_ROOT}/../agentic_quant_platform/aqp/streaming/schemas"
if [[ -d "${AQP_SCHEMAS}" ]]; then
    echo "[build-flink-jobs] syncing Avro schemas from ${AQP_SCHEMAS}"
    mkdir -p "${JOBS_DIR}/jobs/schemas"
    cp "${AQP_SCHEMAS}"/*.avsc "${JOBS_DIR}/jobs/schemas/"
fi

# Multi-arch build. --push requires a registry login.
BUILD_ARGS=(buildx build --platform linux/amd64,linux/arm64 -t "${IMAGE}" "${JOBS_DIR}")
if [[ "${PUSH}" -eq 1 ]]; then
    BUILD_ARGS+=(--push)
else
    BUILD_ARGS+=(--load)
    # --load only supports a single architecture at a time; fall back to
    # the host arch when --push is omitted.
    HOST_ARCH="$(uname -m)"
    case "${HOST_ARCH}" in
        x86_64)  PLATFORM="linux/amd64" ;;
        aarch64|arm64) PLATFORM="linux/arm64" ;;
        *) echo "Unsupported host arch: ${HOST_ARCH}" >&2; exit 3 ;;
    esac
    BUILD_ARGS=(buildx build --platform "${PLATFORM}" -t "${IMAGE}" "${JOBS_DIR}" --load)
fi

echo "[build-flink-jobs] docker ${BUILD_ARGS[*]}"
docker "${BUILD_ARGS[@]}"

if [[ "${SKIP_JOBS}" -ne 1 ]]; then
    if ! command -v mc >/dev/null 2>&1; then
        echo "[build-flink-jobs] WARNING: mc CLI not found; skipping MinIO upload" >&2
    else
        echo "[build-flink-jobs] uploading PyFlink job .py files to ${MC_JOBS_BUCKET}"
        mc mb --ignore-existing "${MC_JOBS_BUCKET}"
        mc cp --recursive "${JOBS_DIR}/jobs/" "${MC_JOBS_BUCKET}/"
        mc cp --recursive "${JOBS_DIR}/jobs/schemas/" "${MC_JOBS_BUCKET}/schemas/"
        echo "[build-flink-jobs] listing:"
        mc ls --recursive "${MC_JOBS_BUCKET}/" | head -40
    fi
fi

echo "[build-flink-jobs] done."
