#!/usr/bin/env bash
# =============================================================================
# Build the Java TA-Lib Flink jobs + push image + upload JARs to MinIO
# =============================================================================
# Usage: bash bootstrap/scripts/build-flink-jobs-java.sh [flags]
#
# Flags:
#   --push                   Also push the multi-arch image to the registry
#   --image <ref>            Override the image reference
#                            (default ghcr.io/julianwiley/flink-trading-java:1.20)
#   --minio-bucket <name>    MinIO bucket to upload JARs to (default flink-jobs)
#   --minio-prefix <path>    Prefix inside the bucket (default java/)
#   --minio-endpoint <url>   MinIO endpoint URL when running from a workstation
#                            (default http://minio.local:9000)
#
# Prerequisites:
#   - docker buildx
#   - gradle wrapper usable (gradlew executes inside the build image)
#   - MinIO `mc` CLI on PATH if JARs are to be uploaded
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SRC_DIR="${REPO_ROOT}/flink-jobs-java"

IMAGE="ghcr.io/julianwiley/flink-trading-java:1.20"
PUSH=0
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio.local:9000}"
MINIO_BUCKET="flink-jobs"
MINIO_PREFIX="java"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --push)            PUSH=1; shift ;;
        --image)           IMAGE="$2"; shift 2 ;;
        --minio-bucket)    MINIO_BUCKET="$2"; shift 2 ;;
        --minio-prefix)    MINIO_PREFIX="$2"; shift 2 ;;
        --minio-endpoint)  MINIO_ENDPOINT="$2"; shift 2 ;;
        *)                 echo "unknown flag: $1" >&2; exit 1 ;;
    esac
done

echo "[INFO] building flink-jobs-java image ${IMAGE}"
cd "${SRC_DIR}"

if [[ "${PUSH}" -eq 1 ]]; then
    docker buildx build --platform linux/amd64,linux/arm64 \
        -t "${IMAGE}" --push .
else
    docker buildx build --platform linux/amd64 --load \
        -t "${IMAGE}" .
fi

# ---------------------------------------------------------------------------
# Extract shadow JARs from the just-built image and upload them to MinIO.
# ---------------------------------------------------------------------------
if command -v mc >/dev/null 2>&1; then
    echo "[INFO] uploading shadow JARs to ${MINIO_ENDPOINT}/${MINIO_BUCKET}/${MINIO_PREFIX}/"
    tmp=$(mktemp -d)
    container=$(docker create "${IMAGE}")
    docker cp "${container}:/opt/flink-java-jobs" "${tmp}/jars"
    docker rm -f "${container}" >/dev/null
    mc alias set aqp "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY:-minioadmin}" "${MINIO_SECRET_KEY:-minioadmin123}" >/dev/null
    mc mb --ignore-existing "aqp/${MINIO_BUCKET}" >/dev/null
    for jar in "${tmp}/jars"/*.jar; do
        mc cp "${jar}" "aqp/${MINIO_BUCKET}/${MINIO_PREFIX}/$(basename "${jar}")"
    done
    rm -rf "${tmp}"
else
    echo "[WARN] MinIO mc CLI not found on PATH; skipping JAR upload."
    echo "       Install from https://min.io/docs/minio/linux/reference/minio-mc.html"
    echo "       and re-run this script, or copy the jars manually:"
    echo "         docker run --rm ${IMAGE} tar -C /opt/flink-java-jobs -cf - . | ..."
fi

echo "[INFO] done."
