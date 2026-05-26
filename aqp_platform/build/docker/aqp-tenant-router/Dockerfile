# =============================================================================
# aqp-tenant-router — cell-routing decision service (Phase 3 §6.4).
#
# Chainguard Wolfi + uv multi-stage build per Phase 2 §5.1
# (RESTRUCTURING_PLAN.md). ``-dev`` builder for native-wheel compiles
# (uvloop + httptools), minimal Wolfi runtime as UID 65532
# (Chainguard's canonical ``nonroot``).
#
# Build:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     --file aqp_platform/build/docker/aqp-tenant-router/Dockerfile \
#     --tag ghcr.io/julianwiley/aqp-tenant-router:dev \
#     .
# Build context is the AQP repo root so we can COPY from aqp_tenant_router/.
# =============================================================================
ARG BUILDPLATFORM
ARG TARGETPLATFORM

# -----------------------------------------------------------------------------
# Stage 1 — builder (Chainguard Python 3.11-dev with apk + uv).
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
        git

COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /usr/local/bin/uv

COPY aqp_tenant_router /app/aqp_tenant_router

# Install into a venv we COPY into the runtime stage.
RUN python -m venv /opt/aqp-tenant-router-venv \
    && /opt/aqp-tenant-router-venv/bin/uv pip install \
        --python /opt/aqp-tenant-router-venv/bin/python \
        -e /app/aqp_tenant_router

# -----------------------------------------------------------------------------
# Stage 2 — runtime (Chainguard Python 3.11, nonroot UID 65532).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11 AS runtime

LABEL org.opencontainers.image.title="aqp-tenant-router" \
      org.opencontainers.image.description="AQP cell-routing decision service (Phase 3 §6.4)" \
      org.opencontainers.image.source="https://github.com/julianwiley/agentic_quant_platform" \
      org.opencontainers.image.licenses="Proprietary"

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/aqp-tenant-router-venv/bin:$PATH

COPY --from=builder /opt/aqp-tenant-router-venv /opt/aqp-tenant-router-venv
COPY --from=builder /app/aqp_tenant_router /app/aqp_tenant_router

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["/opt/aqp-tenant-router-venv/bin/python", "-c", "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).read(); sys.exit(0)"]

# Chainguard's ``cgr.dev/chainguard/python:3.11`` defaults ENTRYPOINT
# to /usr/bin/python; override to call the venv's uvicorn directly.
ENTRYPOINT ["/opt/aqp-tenant-router-venv/bin/uvicorn"]
CMD ["aqp_tenant_router.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--access-log"]
