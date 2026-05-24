# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the AV client first (its /opt location matches the path expected by
# the management backend Dockerfile, for easy layer sharing).
COPY integrations/alphavantage /opt/alphavantage-client
RUN pip install --upgrade pip && pip install /opt/alphavantage-client

# Copy the producer template.
COPY templates/alphavantage-producer/pyproject.toml ./
COPY templates/alphavantage-producer/src ./src

# Ship the Avro schemas inside the image so offline schema registration works.
COPY flink-jobs/jobs/schemas/alphavantage /opt/alphavantage-producer/schemas

RUN pip install .

RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app /opt/alphavantage-producer
USER app

ENV AV_PRODUCER_SCHEMA_DIR=/opt/alphavantage-producer/schemas

EXPOSE 9312

ENTRYPOINT ["python", "-m", "alphavantage_producer"]
