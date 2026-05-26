# =============================================================================
# AQP cloud frontend image — Next.js 14+ App Router standalone server.
#
# Phase 2 §5.1 (RESTRUCTURING_PLAN.md) — Chainguard Wolfi migration.
# Two stages:
#   1. builder    — cgr.dev/chainguard/node:20-dev, runs `pnpm build` -> .next/standalone
#   2. production — cgr.dev/chainguard/node:20, runs `node server.js` on :3000
#
# Multi-arch (linux/amd64, linux/arm64) per aqp-platform.mdc hard rule 4.
#
# Build:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     --file aqp_platform/build/docker/aqp_ui/Dockerfile \
#     --tag ghcr.io/julianwiley/aqp-ui:dev \
#     .
# Build context is the AQP repo root so we can COPY from aqp_ui/.
# =============================================================================
ARG BUILDPLATFORM
ARG TARGETPLATFORM

# -----------------------------------------------------------------------------
# Stage 1 — Next.js production build (Chainguard Node 20 -dev: apk + corepack).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/node:20-dev AS builder

WORKDIR /app
USER root

# Chainguard Node ships with glibc, so the libc6-compat shim that the
# previous Alpine-based image needed is no longer necessary.
ENV PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

# Cache deps separately from source for fast rebuilds.
COPY aqp_ui/package.json aqp_ui/pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else pnpm install --no-frozen-lockfile; fi

COPY aqp_ui/ ./

# Public build-time configuration. NEVER bake secrets into the bundle —
# AUTH0_CLIENT_SECRET, ENTRA_CLIENT_SECRET, AQP_UI_SESSION_SECRET are
# injected at runtime via the Pod's envFrom: secretRef ExternalSecret.
ARG AQP_UI_BASE_URL=https://aqp.fund
ARG AQP_CLAIMS_NAMESPACE=https://aqp.internal/
ARG NEXT_PUBLIC_AQP_UI_VERSION=0.1.0
ENV AQP_UI_BASE_URL=$AQP_UI_BASE_URL \
    AQP_CLAIMS_NAMESPACE=$AQP_CLAIMS_NAMESPACE \
    NEXT_PUBLIC_AQP_UI_VERSION=$NEXT_PUBLIC_AQP_UI_VERSION

RUN pnpm build

# -----------------------------------------------------------------------------
# Stage 2 — Production runtime (Chainguard Node 20, nonroot UID 65532).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/node:20 AS production

LABEL org.opencontainers.image.title="aqp-ui" \
      org.opencontainers.image.description="Cloud-hosted, multi-tenant PaaS frontend for the Agentic Quant Platform" \
      org.opencontainers.image.source="https://github.com/julianwiley/agentic_quant_platform" \
      org.opencontainers.image.licenses="Proprietary"

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone server is self-contained (only node_modules it actually
# imports). Static assets go to /app/.next/static and /app/public.
# Chainguard's ``cgr.dev/chainguard/node:20`` runs as UID 65532 by
# default; --chown ensures the runtime user owns its files.
COPY --from=builder --chown=65532:65532 /app/public ./public
COPY --from=builder --chown=65532:65532 /app/.next/standalone ./
COPY --from=builder --chown=65532:65532 /app/.next/static ./.next/static

USER 65532:65532

EXPOSE 3000

# Chainguard's Node runtime omits tini. Kubernetes handles PID 1
# signal forwarding via terminationGracePeriodSeconds; for standalone
# ``docker run`` use ``docker run --init`` to inject a tini-equivalent
# init process.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD ["node", "-e", "require('http').get('http://127.0.0.1:3000/api/healthz', r=>{process.exit(r.statusCode===200?0:1)}).on('error',()=>process.exit(1))"]

# Chainguard's ``cgr.dev/chainguard/node:20`` defaults ENTRYPOINT to
# /usr/bin/node; CMD specifies the script path.
ENTRYPOINT ["/usr/bin/node"]
CMD ["server.js"]
