# /build/ — image build artifacts

Owns the multi-stage Dockerfiles for every AQP-released container image plus the helper scripts that generate environment configuration from the canonical `.env.schema`.

## Structure

```
build/
├── docker/
│   ├── aqp_client/         # Unified client (Vite + Solara + FastAPI gateway)
│   ├── aqp_control_plane/  # Standalone control-plane micro-project
│   ├── aqp_worker/         # ML / RL / backtest Celery worker image
│   └── aqp_ingestion/      # GDelt + BigQuery + Alpha Vantage ingestion pipeline
└── scripts/
    └── generate_config.py  # Emits .env files + K8s ConfigMap / Secret YAML
```

## Ownership

- `docker/aqp_client/` — Platform team (frontend + backend gateway)
- `docker/aqp_control_plane/` — Platform team (isolated micro-project; cf. ADR 005)
- `docker/aqp_worker/` — Compute team (consumes `aqp.tasks.*`)
- `docker/aqp_ingestion/` — Data team (consumes `aqp.data.*` + `aqp.providers.*`)
- `scripts/` — Platform team

## Invariants

- Every `Dockerfile` MUST be reproducible via `docker buildx build --platform linux/amd64,linux/arm64`
- Every image MUST have a `HEALTHCHECK` directive
- Every image MUST set a non-root user (`USER 1000` or equivalent)
- Build context is the AQP repo root (so the Dockerfiles can `COPY` from `aqp/`, `aqp_platform_core/`, `aqp_client/`, etc.)
- Image tags follow `ghcr.io/julianwiley/<name>:<env>-<gitsha>-<isodate>` with `env` in `{dev,staging,prod}`

## Cross-reference

- [ADR 001 — static export over SSR](../docs/architecture/decisions/001-static-export-over-ssr.md)
- [ADR 002 — single container client](../docs/architecture/decisions/002-single-container-client.md)
- [ADR 005 — separated control plane](../docs/architecture/decisions/005-separated-control-plane.md)
