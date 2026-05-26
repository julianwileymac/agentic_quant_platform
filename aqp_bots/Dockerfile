# syntax=docker/dockerfile:1.7
# QuantBot Platform — standard distroless bot runtime.
#
# Phase 2 §5.1 EXEMPTION (RESTRUCTURING_PLAN.md, .cursor/plans/
# aqp-index-debt-phase-2-supply-chain.md):
# This image deliberately does NOT migrate to cgr.dev/chainguard/python.
# Distroless ``gcr.io/distroless/python3-debian12:nonroot`` is already
# smaller, has no shell, has no apk/apt, and is reachable by the same
# class of supply-chain attacks Chainguard mitigates — the migration
# would trade one verified-minimal runtime for another at no benefit.
# The builder stage is still a slim-bookworm image; future work tracked
# at aqp-index-debt-phase-2-supply-chain.md can re-evaluate.
#
# Multi-stage build with uv. Target image size < 200 MiB; UID 65532
# (distroless ``nonroot``), read-only root FS, ALL caps dropped.
# Per blueprint §N.

# ============== STAGE 1: builder ==============
FROM python:3.12-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /uvx /bin/

# Tooling needed by some wheels (cleanup at the end).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN uv python install 3.12

WORKDIR /app

# 1) Install dependencies WITHOUT the project itself (caching).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=aqp_bots/uv.lock,target=uv.lock \
    --mount=type=bind,source=aqp_bots/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --no-editable

# 2) Copy source code and install the project.
COPY aqp_bots /app/aqp_bots
COPY aqp /app/aqp
COPY aqp_platform_core /app/aqp_platform_core

RUN --mount=type=cache,target=/root/.cache/uv \
    cd /app/aqp_bots && uv sync --frozen --no-dev --no-editable

# ============== STAGE 2: runtime (distroless) ==============
FROM gcr.io/distroless/python3-debian12:nonroot AS runtime

COPY --from=builder /python /python
COPY --from=builder /app/aqp_bots/.venv /app/.venv
COPY --from=builder /app/aqp_bots /app/aqp_bots
COPY --from=builder /app/aqp /app/aqp
COPY --from=builder /app/aqp_platform_core /app/aqp_platform_core

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app:/app/aqp_bots:/app/aqp_platform_core/src \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AQP_BOTS_LOG_LEVEL=INFO

WORKDIR /app

USER 65532:65532

EXPOSE 9090

# Default to the bot CLI; the operator's rendered Pod overrides this
# via container.args (e.g. ["python", "-m", "aqp_bots.cli", "run", "<slug>"]).
ENTRYPOINT ["/app/.venv/bin/python", "-m", "aqp_bots.cli"]
