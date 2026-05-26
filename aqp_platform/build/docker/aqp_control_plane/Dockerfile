# =============================================================================
# AQP control-plane sidecar image (aqp_control_plane + aqp_platform_core only).
#
# Phase 2 §5.1 (RESTRUCTURING_PLAN.md) — Chainguard Wolfi + uv multi-stage.
# ``-dev`` builder for native-wheel compiles, minimal Wolfi runtime as
# UID 65532 (Chainguard's canonical ``nonroot``).
#
# Build:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     --file aqp_platform/build/docker/aqp_control_plane/Dockerfile \
#     --tag ghcr.io/julianwiley/aqp-control-plane:dev \
#     .
# Build context is the AQP repo root so we can COPY from aqp_platform_core/.
# =============================================================================
ARG BUILDPLATFORM
ARG TARGETPLATFORM

# -----------------------------------------------------------------------------
# Stage 1 — builder (Chainguard Python 3.11-dev with apk + uv + native-wheel
# build tooling).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11-dev AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

USER root
RUN apk add --no-cache \
        build-base \
        curl \
        git \
        postgresql-dev

COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /usr/local/bin/uv

COPY aqp_platform_core ./aqp_platform_core
COPY aqp_control_plane ./aqp_control_plane

# Install into a venv that we COPY into the runtime stage. This gives
# us a clean separation from the dev image's apk-managed paths and
# keeps the runtime layer minimal.
RUN python -m venv /opt/aqp-cp-venv \
    && /opt/aqp-cp-venv/bin/uv pip install --python /opt/aqp-cp-venv/bin/python \
        -e ./aqp_platform_core \
        -e "./aqp_control_plane[kubernetes]"

# -----------------------------------------------------------------------------
# Stage 2 — runtime (Chainguard Python 3.11, nonroot UID 65532).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11 AS runtime

LABEL org.opencontainers.image.title="aqp-control-plane" \
      org.opencontainers.image.description="AQP standalone control plane (/manage/* API)" \
      org.opencontainers.image.source="https://github.com/julianwiley/agentic_quant_platform" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/aqp-cp-venv/bin:$PATH

WORKDIR /app

COPY --from=builder /opt/aqp-cp-venv /opt/aqp-cp-venv
COPY --from=builder /app/aqp_platform_core /app/aqp_platform_core
COPY --from=builder /app/aqp_control_plane /app/aqp_control_plane

USER 65532:65532

EXPOSE 9000

# Chainguard's ``cgr.dev/chainguard/python:3.11`` defaults ENTRYPOINT
# to /usr/bin/python; override to invoke the venv's uvicorn directly.
ENTRYPOINT ["/opt/aqp-cp-venv/bin/uvicorn"]
CMD ["aqp_cp.main:app", "--host", "0.0.0.0", "--port", "9000"]
