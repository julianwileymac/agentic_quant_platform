# --- builder ---------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

ENV PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

COPY package.json pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else pnpm install --no-frozen-lockfile; fi

COPY . .

ARG VITE_API_URL=http://localhost:8000
ARG VITE_WS_URL=ws://localhost:8000
ARG VITE_DEFAULT_MODE=live
ENV VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL \
    VITE_DEFAULT_MODE=$VITE_DEFAULT_MODE

RUN pnpm build

# --- runner ----------------------------------------------------------------
# Vite preview is fine for the dev compose; production deployments behind a
# reverse proxy should serve `dist/` as static assets and proxy /aqp-api +
# /aqp-ws to FastAPI.
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

COPY --from=builder /app/package.json /app/pnpm-lock.yaml* ./
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3001
CMD ["pnpm", "preview", "--host", "0.0.0.0"]
