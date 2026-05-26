###############################################################################
# AQP master Dockerfile (Chainguard Wolfi + uv).
#
# Phase 2 §5.1 (RESTRUCTURING_PLAN.md) Chainguard Wolfi migration. The
# base layer pins ``cgr.dev/chainguard/python:3.11-dev`` (Wolfi-based
# glibc Python distribution; required for native numpy / pyarrow / torch
# wheels), and every install step routes through ``uv pip install``
# instead of bare pip for reproducibility + cache hit rate. The
# matching ``uv sync --frozen`` migration (RESTRUCTURING_PLAN.md
# §5.1 recommendation) requires a committed ``uv.lock`` at the repo
# root, which is captured as a Phase 2.5 follow-up in
# ``.cursor/plans/aqp-index-debt-phase-2-supply-chain.md``.
#
# Phase 4c control-plane maturation: multi-arch (linux/amd64 +
# linux/arm64) build via:
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     --target api --tag docker.io/julianwiley/aqp-api:<tag> --push .
# The ``$BUILDPLATFORM`` ARG is auto-populated by buildx when running
# under buildx; falls back to the build host's native arch otherwise.
#
# Phase 2 §5.4 — every final stage runs as UID 65532 (Chainguard's
# canonical ``nonroot`` UID). Matching Pod-spec ``runAsUser: 65532``
# is wired in the Phase 2 PSS backfill at
# ``aqp_platform/deployments/kubernetes/base/<service>/deployment.yaml``.
###############################################################################
ARG BUILDPLATFORM
ARG TARGETPLATFORM

###############################################################################
# Stage 1: shared base with system deps.
#
# ``-dev`` variant ships apk + bash + build-base + linux-headers so
# native wheels (numpy, pyarrow, torch, psycopg2) compile cleanly. The
# image is Wolfi-glibc, not Alpine-musl, so the native-wheel
# compatibility caveat from the RESTRUCTURING_PLAN footnote applies.
###############################################################################
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11-dev AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Chainguard ``-dev`` images run as root by default so apk works; the
# final runtime ``USER 65532`` directive in each target stage drops
# privileges. apk add equivalents for the prior Debian set
# (build-essential, curl, docker.io, docker-compose, git, libpq-dev,
# postgresql-client). ``docker-cli`` + ``docker-compose`` are required
# by ``aqp/cli/deploy_cmd.py`` and ``aqp/kubernetes/adapters/local_compose.py``
# at runtime — keep them in the base image until those CLIs move
# behind a feature-flagged extra.
USER root
RUN apk add --no-cache \
        build-base \
        gcc \
        gfortran \
        linux-headers \
        curl \
        git \
        docker-cli \
        docker-compose \
        postgresql-dev \
        postgresql-client

# uv ships as a standalone static binary; pull from the official
# image and drop into /usr/local/bin so every subsequent stage picks
# it up via ``$PATH``.
COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /usr/local/bin/uv

COPY pyproject.toml ./
COPY README.md ./
COPY aqp_platform_core ./aqp_platform_core
COPY aqp ./aqp
COPY aqp_bots ./aqp_bots
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./

###############################################################################
# Stage 2: "paper" target — paper/live trading engine with all broker extras.
# Ships with alpaca-py, ib-async, httpx (Tradier), tenacity and full OTel.
# Built explicitly via docker-compose ``target: paper``.
###############################################################################
FROM base AS paper

RUN uv pip install --system -e ./aqp_platform_core \
    && uv pip install --system -e ".[alpaca,ibkr,tradier,otel,cli,paper,streaming]"

RUN mkdir -p /app/data \
    && chown -R 65532:65532 /app
USER 65532:65532

EXPOSE 9100

ENTRYPOINT []
CMD ["aqp", "paper", "run", "--config", "/etc/aqp/paper.yaml"]


###############################################################################
# Stage 2b: "ingester" target — long-lived streaming ingester that connects to
# IB Gateway + Alpaca WebSocket and publishes canonical Avro records to Kafka.
# Used by the aqp_platform/deploy/k8s/base/ingester-*.yaml Deployments.
###############################################################################
FROM base AS ingester

RUN uv pip install --system -e ./aqp_platform_core \
    && uv pip install --system -e ".[alpaca,ibkr,streaming,otel]"

RUN chown -R 65532:65532 /app
USER 65532:65532

# 9300 = Prometheus metrics, 9301 = /healthz (aiohttp)
EXPOSE 9300 9301

ENTRYPOINT []
CMD ["aqp-stream-ingest", "--venue", "all"]


###############################################################################
# Stage 3 (default): "api" target — FastAPI gateway + UI-capable runtime with
# Dash mounted at /dash and full dev extras so the worker / UI containers
# share this image.
###############################################################################
FROM base AS api

# Phase 0 — adds the [auth] extra so python-jose ships in the API image
# and OIDC validate_jwt() works when AQP_AUTH_PROVIDER=oidc. boto3
# (for MinIO uploads) comes in transitively via [iceberg] -> s3fs ->
# botocore; the DatasetManager has a local-fs fallback when neither
# boto3 nor MinIO endpoints are configured.
RUN uv pip install --system -e ./aqp_platform_core \
    && uv pip install --system -e ".[auth,dev,otel,cli,iceberg,visualization,entity-graph,dagster-aqp,compute-dask,compute-ray]"

RUN chown -R 65532:65532 /app
USER 65532:65532

EXPOSE 8000 8765

ENTRYPOINT []
CMD ["uvicorn", "aqp.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


###############################################################################
# Stage 4: "serving" target — model inference runtime with all serving
# backends (MLflow Serve, Ray Serve, TorchServe) and the torch model zoo
# pre-installed. Used by aqp_platform/deploy/k8s/base/serving-*.yaml Deployments.
###############################################################################
FROM base AS serving

RUN uv pip install --system -e ".[ml,ml-torch,ml-forecast,ml-anomaly,portfolio,serving-mlflow,serving-ray,otel,cli]"

RUN mkdir -p /app/data /app/models \
    && chown -R 65532:65532 /app
USER 65532:65532

# 8000 = Ray Serve HTTP, 8080 = TorchServe inference, 8081 = TorchServe mgmt,
# 5001 = MLflow Serve default.
EXPOSE 5001 8000 8080 8081

ENTRYPOINT []
CMD ["aqp", "serve", "mlflow", "--help"]


###############################################################################
# Stage 5: "ml-train" target — training runtime for CI jobs / Ray Tune sweeps.
# Installs the ``full`` extra so every phase's code works.
###############################################################################
FROM base AS ml-train

RUN uv pip install --system -e ".[ml,ml-torch,ml-forecast,ml-anomaly,portfolio,otel,cli,iceberg,entity-graph,dagster-aqp]"

RUN mkdir -p /app/data \
    && chown -R 65532:65532 /app
USER 65532:65532

ENTRYPOINT []
CMD ["aqp-train", "--help"]
