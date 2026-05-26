# =============================================================================
# AQP unified client image — Vite + Solara + FastAPI gateway in ONE container.
#
# Phase 2 §5.1 (RESTRUCTURING_PLAN.md) — Chainguard Wolfi migration.
# Three stages:
#   1. ui-builder      — cgr.dev/chainguard/node:20-dev, builds Vite SPA -> /app/out/
#   2. solara-builder  — cgr.dev/chainguard/python:3.11-dev, pre-warms Solara legacy UI
#   3. production      — cgr.dev/chainguard/python:3.11, FastAPI runtime; no Node, no npm
#
# Runtime stage runs as UID 65532 (Chainguard ``nonroot``). The
# matching Pod spec at
# ``aqp_platform/deployments/kubernetes/base/aqp-client/deployment.yaml``
# sets ``runAsUser: 65532`` (Phase 2 §5.4 PSS backfill).
#
# See:
#   docs/architecture/decisions/001-static-export-over-ssr.md
#   docs/architecture/decisions/002-single-container-client.md
#
# Build:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     --file build/docker/aqp_client/Dockerfile \
#     --tag ghcr.io/julianwiley/aqp-client:dev \
#     .
# Build context is the AQP repo root so we can COPY from aqp_client/, aqp/, etc.
# =============================================================================
ARG BUILDPLATFORM
ARG TARGETPLATFORM

# -----------------------------------------------------------------------------
# Stage 1 — Vite UI bundle (Chainguard Node 20 with corepack + apk).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/node:20-dev AS ui-builder

WORKDIR /app
USER root

# Chainguard Node ships corepack (bundled with Node >= 16.10). Activate
# pnpm at the version the lockfile expects.
ENV PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

# Copy lockfile first so npm-side dep changes invalidate cache cleanly.
COPY aqp_client/package.json aqp_client/pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else pnpm install --no-frozen-lockfile; fi

COPY aqp_client/ ./

# All backend URLs are relative — the SPA always routes through the FastAPI
# gateway in stage 3 via /api, /ml, /mcp, /manage, /ws.
ARG VITE_AQP_API_BASE_URL=/api
ARG VITE_AQP_AUTH0_DOMAIN=
ARG VITE_AQP_AUTH0_CLIENT_ID=
ARG VITE_AQP_AUTH0_AUDIENCE=https://api.aqp.internal/manage
ENV VITE_AQP_API_BASE_URL=$VITE_AQP_API_BASE_URL \
    VITE_AQP_AUTH0_DOMAIN=$VITE_AQP_AUTH0_DOMAIN \
    VITE_AQP_AUTH0_CLIENT_ID=$VITE_AQP_AUTH0_CLIENT_ID \
    VITE_AQP_AUTH0_AUDIENCE=$VITE_AQP_AUTH0_AUDIENCE

RUN pnpm build

# Move output to a predictable path consumed by stage 3.
RUN mkdir -p /app/out && cp -r dist/* /app/out/

# -----------------------------------------------------------------------------
# Stage 2 — Solara legacy UI cache (Chainguard Python 3.11-dev).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11-dev AS solara-builder

WORKDIR /build
USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apk add --no-cache build-base

# Install Solara and a minimum stub of AQP so the legacy UI module is importable.
# We do NOT install the full AQP runtime here — the production stage handles that.
RUN pip install --upgrade pip \
 && pip install "solara>=1.31,<2" "starlette>=0.36,<1" "uvicorn>=0.27,<1"

# Pre-touch the Solara cache directory so the production image inherits a
# warmed-up structure instead of generating it on first request.
RUN mkdir -p /opt/solara-cache \
 && SOLARA_TEMP_DIR=/opt/solara-cache python -c "import solara; print('solara import OK')"

# -----------------------------------------------------------------------------
# Stage 3a — Production-deps builder (Chainguard Python 3.11-dev).
#
# We split the install + runtime into separate stages so the final
# image stays lean (no apk, no compiler toolchain, no curl-as-init).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11-dev AS production-builder

WORKDIR /app
USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

RUN apk add --no-cache build-base curl

COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /usr/local/bin/uv

COPY aqp_platform_core/ /app/aqp_platform_core/
COPY aqp/ /app/aqp/
COPY aqp_bots/ /app/aqp_bots/
COPY pyproject.toml /app/pyproject.toml

# Install into an isolated venv that we COPY into the runtime stage.
RUN python -m venv /opt/aqp-client-venv \
 && /opt/aqp-client-venv/bin/uv pip install --python /opt/aqp-client-venv/bin/python \
        -e /app/aqp_platform_core \
 && /opt/aqp-client-venv/bin/uv pip install --python /opt/aqp-client-venv/bin/python \
        "fastapi>=0.115,<1" \
        "uvicorn[standard]>=0.27,<1" \
        "httpx>=0.27,<1" \
        "websockets>=12,<14" \
        "python-jose[cryptography]>=3.3,<4" \
        "PyYAML>=6,<7"

# -----------------------------------------------------------------------------
# Stage 3b — Production runtime (Chainguard Python 3.11, nonroot UID 65532).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11 AS production

LABEL org.opencontainers.image.title="aqp-client" \
      org.opencontainers.image.description="Unified AQP client — Vite SPA + Solara legacy + FastAPI gateway" \
      org.opencontainers.image.source="https://github.com/julianwiley/agentic_quant_platform" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/aqp-client-venv/bin:$PATH \
    AQP_CLIENT_MODE=true \
    AQP_CLIENT_STATIC_DIR=/app/static \
    AQP_CLIENT_LEGACY_DIR=/app/legacy_ui \
    AQP_CLIENT_WEBUI_DIR=/app/webui_legacy

WORKDIR /app

# Bring in the venv + the application source from the builder.
COPY --from=production-builder /opt/aqp-client-venv /opt/aqp-client-venv
COPY --from=production-builder /app/aqp_platform_core /app/aqp_platform_core
COPY --from=production-builder /app/aqp /app/aqp
COPY --from=production-builder /app/aqp_bots /app/aqp_bots
COPY --from=production-builder /app/pyproject.toml /app/pyproject.toml

# Static assets — Vite output from stage 1.
COPY --from=ui-builder /app/out/ /app/static/

# Solara legacy UI surface. The aqp/ui module ships with the AQP source tree,
# so this is the same Python package the production worker uses.
COPY --from=solara-builder /opt/solara-cache /opt/solara-cache

# Chainguard's ``nonroot`` user is already UID 65532; no useradd/groupadd
# needed. Drop a process tree owned by the same UID.
USER 65532:65532

EXPOSE 8080

# Note: Chainguard's runtime image omits tini. Kubernetes handles PID 1
# signal forwarding via terminationGracePeriodSeconds + shareProcessNamespace.
# For standalone ``docker run`` use ``docker run --init`` to inject a
# tini-equivalent init process.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD ["/opt/aqp-client-venv/bin/python", "-c", "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).read(); sys.exit(0)"]

# Chainguard's ``cgr.dev/chainguard/python:3.11`` defaults ENTRYPOINT to
# /usr/bin/python; override to use the venv's uvicorn binary directly.
ENTRYPOINT ["/opt/aqp-client-venv/bin/uvicorn"]
CMD ["aqp.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
