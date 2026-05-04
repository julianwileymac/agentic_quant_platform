# --- builder ---------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

ENV PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

RUN corepack enable

COPY package.json pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else pnpm install --no-frozen-lockfile; fi

COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ARG NEXT_PUBLIC_DASH_URL=http://localhost:8000/dash/
ARG NEXT_PUBLIC_MLFLOW_URL=http://localhost:5000
ARG NEXT_PUBLIC_JAEGER_URL=http://localhost:16686
ARG NEXT_PUBLIC_SUPERSET_URL=http://localhost:8088
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    NEXT_PUBLIC_DASH_URL=$NEXT_PUBLIC_DASH_URL \
    NEXT_PUBLIC_MLFLOW_URL=$NEXT_PUBLIC_MLFLOW_URL \
    NEXT_PUBLIC_JAEGER_URL=$NEXT_PUBLIC_JAEGER_URL \
    NEXT_PUBLIC_SUPERSET_URL=$NEXT_PUBLIC_SUPERSET_URL

RUN pnpm build

# --- runner ----------------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

RUN corepack enable

COPY --from=builder /app/package.json /app/pnpm-lock.yaml* ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3000
CMD ["pnpm", "start"]
