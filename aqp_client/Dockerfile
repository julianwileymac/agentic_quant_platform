# =============================================================================
# AQP unified client image — Vite + Solara + FastAPI gateway in ONE container.
#
# Three stages:
#   1. ui-builder      — node:20-alpine, builds the Vite SPA -> /app/out/
#   2. solara-builder  — python:3.11-slim, pre-warms Solara legacy UI deps
#   3. production      — python:3.11-slim, FastAPI runtime; NO Node, NO npm
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

# -----------------------------------------------------------------------------
# Stage 1 — Vite UI bundle
# -----------------------------------------------------------------------------
FROM node:20-alpine AS ui-builder

WORKDIR /app

ENV PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

# Copy lockfile first so npm-side dep changes invalidate cache cleanly.
COPY aqp_client/package.json aqp_client/pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else pnpm install --no-frozen-lockfile; fi

COPY aqp_client/ ./

# Host bind-mounts can leave a foreign node_modules tree in the context; the
# repo-root .dockerignore excludes it, but reinstall defensively for linux.
RUN rm -rf node_modules \
    && if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else pnpm install --no-frozen-lockfile; fi

# Vite reads VITE_* at build time (must match deployments/kubernetes ConfigMap).
ARG VITE_API_URL=https://api.aqp.fund
ARG VITE_WS_URL=wss://api.aqp.fund
ARG VITE_AUTH0_DOMAIN=aqp-fund.us.auth0.com
ARG VITE_AUTH0_CLIENT_ID=
ARG VITE_AUTH0_AUDIENCE=https://api.aqp.internal/manage
ARG VITE_AUTH0_REDIRECT_URI=https://aqp.fund
ENV VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL \
    VITE_AUTH0_DOMAIN=$VITE_AUTH0_DOMAIN \
    VITE_AUTH0_CLIENT_ID=$VITE_AUTH0_CLIENT_ID \
    VITE_AUTH0_AUDIENCE=$VITE_AUTH0_AUDIENCE \
    VITE_AUTH0_REDIRECT_URI=$VITE_AUTH0_REDIRECT_URI

RUN pnpm run build

# Move output to a predictable path consumed by stage 3.
RUN mkdir -p /app/out && cp -r dist/* /app/out/

# -----------------------------------------------------------------------------
# Stage 2 — Solara legacy UI cache
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS solara-builder

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install Solara and a minimum stub of AQP so the legacy UI module is importable.
# We do NOT install the full AQP runtime here — the production stage handles that.
RUN pip install --upgrade pip \
 && pip install "solara>=1.31,<2" "starlette>=0.36,<1" "uvicorn>=0.27,<1"

# Pre-touch the Solara cache directory so the production image inherits a
# warmed-up structure instead of generating it on first request.
RUN mkdir -p /opt/solara-cache \
 && SOLARA_TEMP_DIR=/opt/solara-cache python -c "import solara; print('solara import OK')"

# -----------------------------------------------------------------------------
# Stage 3 — Production runtime (FastAPI gateway)
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS production

LABEL org.opencontainers.image.title="aqp-client" \
      org.opencontainers.image.description="Unified AQP client — Vite SPA + Solara legacy + FastAPI gateway" \
      org.opencontainers.image.source="https://github.com/julianwiley/agentic_quant_platform" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    AQP_CLIENT_MODE=true \
    AQP_CLIENT_STATIC_DIR=/app/static \
    AQP_CLIENT_LEGACY_DIR=/app/legacy_ui \
    AQP_CLIENT_WEBUI_DIR=/app/webui_legacy

WORKDIR /app

# Slim runtime deps. The gateway is HTTP/WS only — no SQLAlchemy / Celery /
# numerical stack required, those live in aqp_worker / aqp_core images.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        tini \
 && rm -rf /var/lib/apt/lists/*

# aqp_platform_core supplies ConnectivityConfig + JWT validator. We need
# enough of aqp/ to mount the FastAPI app + proxy + ws_proxy modules.
COPY aqp_platform_core/ /app/aqp_platform_core/
COPY aqp/ /app/aqp/
COPY aqp_bots/ /app/aqp_bots/
COPY pyproject.toml /app/pyproject.toml

RUN pip install --upgrade pip \
 && pip install -e /app/aqp_platform_core \
 && pip install \
        "fastapi>=0.115,<1" \
        "uvicorn[standard]>=0.27,<1" \
        "httpx>=0.27,<1" \
        "websockets>=12,<14" \
        "python-jose[cryptography]>=3.3,<4" \
        "PyYAML>=6,<7"

# Static assets — Vite output from stage 1.
COPY --from=ui-builder /app/out/ /app/static/

# Solara legacy UI surface. The aqp/ui module ships with the AQP source tree,
# so this is the same Python package the production worker uses.
COPY --from=solara-builder /opt/solara-cache /opt/solara-cache

# Non-root user (Pod Security Standards "restricted").
RUN groupadd -r aqp --gid 1000 \
 && useradd -r -g aqp --uid 1000 --home /app --shell /sbin/nologin aqp \
 && chown -R aqp:aqp /app /opt/solara-cache

USER 1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "aqp.api.client_main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
