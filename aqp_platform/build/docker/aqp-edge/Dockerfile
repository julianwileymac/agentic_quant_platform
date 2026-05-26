# =============================================================================
# aqp-edge — Envoy-based cell router.
#
# Phase 2 §5.1 (RESTRUCTURING_PLAN.md) creates this scaffold to reserve
# the image name and unblock parallel Phase 3 work. The actual cell
# router configuration is filled in during Phase 3 (cell topology over
# existing tenancy strategies) per RESTRUCTURING_PLAN.md §6.4 and
# Phase 5 (`Cell-Bound-Authorization` validation) per §8.5.
#
# Until Phase 3 lands, this image is a thin Envoy v1.30 distroless
# layer that boots with a no-op configuration (`drop-all`). Use the
# canonical Phase 3 build script at
# ``aqp_platform/scripts/cluster_install/install-edge.sh`` once it
# exists; the scaffold here only proves the build matrix.
#
# Build:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     --file aqp_platform/build/docker/aqp-edge/Dockerfile \
#     --tag ghcr.io/julianwiley/aqp-edge:dev \
#     .
# Build context is the AQP repo root so Phase 3 can COPY the
# generated Envoy config from build/docker/aqp-edge/envoy.template.yaml.
# =============================================================================
ARG BUILDPLATFORM
ARG TARGETPLATFORM

# Envoy ships its own distroless image with the binary at /usr/local/bin/envoy.
# Pin to a v1.30.x release; refresh on a quarterly cadence via Renovate
# (Phase 1 §4.7) once the cell router lands in Phase 3.
FROM --platform=$TARGETPLATFORM envoyproxy/envoy:distroless-v1.30-latest AS runtime

LABEL org.opencontainers.image.title="aqp-edge" \
      org.opencontainers.image.description="AQP cell router (Envoy) - Phase 3 §6.4 stub" \
      org.opencontainers.image.source="https://github.com/julianwiley/agentic_quant_platform" \
      org.opencontainers.image.licenses="Proprietary"

# Drop the Phase 3 cell-router template. Operators MUST mount a real
# config via a Kubernetes ConfigMap before this image is fit for
# anything beyond the build-matrix smoke test.
COPY aqp_platform/build/docker/aqp-edge/envoy.template.yaml /etc/envoy/envoy.yaml

# Envoy distroless image already runs as nonroot UID 101 (the
# ``envoy`` user). Pinning to UID 65532 for consistency with the
# Phase 2 §5.4 PSS convention requires a custom build of the Envoy
# image — out of scope for the Phase 2 scaffold. Document this as the
# single explicit exception in the Phase 2 §5.4 PSS backfill.
USER 65532:65532

EXPOSE 10000

ENTRYPOINT ["/usr/local/bin/envoy"]
CMD ["-c", "/etc/envoy/envoy.yaml", "--service-cluster", "aqp-edge"]
