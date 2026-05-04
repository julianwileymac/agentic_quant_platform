###############################################################################
# Stage 1: shared base with system deps.
###############################################################################
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY README.md ./
COPY aqp ./aqp
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./

###############################################################################
# Stage 2: "paper" target — paper/live trading engine with all broker extras.
# Ships with alpaca-py, ib-async, httpx (Tradier), tenacity and full OTel.
# Built explicitly via docker-compose ``target: paper``.
###############################################################################
FROM base AS paper

RUN pip install --upgrade pip && pip install -e ".[alpaca,ibkr,tradier,otel,cli,paper,streaming]"

RUN useradd --system --uid 1001 aqp \
    && mkdir -p /app/data \
    && chown -R aqp:aqp /app
USER aqp

EXPOSE 9100

CMD ["aqp", "paper", "run", "--config", "/etc/aqp/paper.yaml"]


###############################################################################
# Stage 2b: "ingester" target — long-lived streaming ingester that connects to
# IB Gateway + Alpaca WebSocket and publishes canonical Avro records to Kafka.
# Used by the deploy/k8s/base/ingester-*.yaml Deployments.
###############################################################################
FROM base AS ingester

RUN pip install --upgrade pip && pip install -e ".[alpaca,ibkr,streaming,otel]"

RUN useradd --system --uid 1001 aqp \
    && chown -R aqp:aqp /app
USER aqp

# 9300 = Prometheus metrics, 9301 = /healthz (aiohttp)
EXPOSE 9300 9301

CMD ["aqp-stream-ingest", "--venue", "all"]


###############################################################################
# Stage 3 (default): "api" target — FastAPI gateway + UI-capable runtime with
# Dash mounted at /dash and full dev extras so the worker / UI containers
# share this image.
###############################################################################
FROM base AS api

RUN pip install --upgrade pip && pip install -e ".[dev,otel,cli,iceberg,visualization,entity-graph,dagster-aqp]"

EXPOSE 8000 8765

CMD ["uvicorn", "aqp.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


###############################################################################
# Stage 4: "serving" target — model inference runtime with all serving
# backends (MLflow Serve, Ray Serve, TorchServe) and the torch model zoo
# pre-installed. Used by deploy/k8s/base/serving-*.yaml Deployments.
###############################################################################
FROM base AS serving

RUN pip install --upgrade pip \
    && pip install -e ".[ml,ml-torch,ml-forecast,ml-anomaly,portfolio,serving-mlflow,serving-ray,otel,cli]"

RUN useradd --system --uid 1001 aqp \
    && mkdir -p /app/data /app/models \
    && chown -R aqp:aqp /app
USER aqp

# 8000 = Ray Serve HTTP, 8080 = TorchServe inference, 8081 = TorchServe mgmt,
# 5001 = MLflow Serve default.
EXPOSE 5001 8000 8080 8081

CMD ["aqp", "serve", "mlflow", "--help"]


###############################################################################
# Stage 5: "ml-train" target — training runtime for CI jobs / Ray Tune sweeps.
# Installs the ``full`` extra so every phase's code works.
###############################################################################
FROM base AS ml-train

RUN pip install --upgrade pip && pip install -e ".[ml,ml-torch,ml-forecast,ml-anomaly,portfolio,otel,cli,iceberg,entity-graph,dagster-aqp]"

RUN useradd --system --uid 1001 aqp \
    && mkdir -p /app/data \
    && chown -R aqp:aqp /app
USER aqp

CMD ["aqp-train", "--help"]
