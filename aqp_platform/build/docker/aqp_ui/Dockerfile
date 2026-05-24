# =============================================================================
# AQP cloud frontend image — Next.js 14+ App Router standalone server.
#
# Two stages:
#   1. builder    — node:20-alpine, runs `pnpm build` -> .next/standalone
#   2. production — node:20-alpine, runs `node server.js` on :3000
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

ARG NODE_VERSION=20

# -----------------------------------------------------------------------------
# Stage 1 — Next.js production build
# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS builder

WORKDIR /app

# libc6-compat fixes occasional musl/glibc shim issues with native modules
# pulled in by @azure/msal-node and @ant-design/icons.
RUN apk add --no-cache libc6-compat

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
# Stage 2 — Production runtime (Next.js standalone server)
# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS production

LABEL org.opencontainers.image.title="aqp-ui" \
      org.opencontainers.image.description="Cloud-hosted, multi-tenant PaaS frontend for the Agentic Quant Platform" \
      org.opencontainers.image.source="https://github.com/julianwiley/agentic_quant_platform" \
      org.opencontainers.image.licenses="Proprietary"

WORKDIR /app

RUN apk add --no-cache tini curl

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Non-root user matching the aqp_client / aqp_admin convention.
RUN addgroup --system --gid 1000 nodejs \
 && adduser --system --uid 1000 --ingroup nodejs nextjs

# Standalone server is self-contained (only node_modules it actually
# imports). Static assets go to /app/.next/static and /app/public.
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER 1000

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:3000/api/healthz || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "server.js"]
