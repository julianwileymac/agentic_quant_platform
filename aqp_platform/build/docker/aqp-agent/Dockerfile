###############################################################################
# aqp-agent — ARM64-only image for Amazon Bedrock AgentCore Runtime.
#
# Amazon Bedrock AgentCore Runtime is ARM64-only per the AWS Builders
# walkthrough on dev.to ("Terraform Your AWS AgentCore"). Building this
# Dockerfile multi-arch would waste CI minutes and still ship the
# wrong slice to AgentCore.
#
# Build:
#   docker buildx build --platform linux/arm64 \
#     --file aqp_platform/build/docker/aqp-agent/Dockerfile \
#     --tag ${ECR_REGISTRY}/aqp-agent:<git-sha> \
#     --push .
#
# The image is rooted in the same Chainguard Wolfi base as the rest of
# the AQP stack (Python 3.11 dev for native wheels). The final entrypoint
# is the AgentCore-shaped invocation handler at
# ``aqp.agents.agentcore_entrypoint`` — it reads the AgentCore Runtime
# invocation envelope from stdin, dispatches into AgentRuntime, and
# streams the response back to AgentCore.
#
# Per the management-engine credential-safety rule: NEVER bake a token
# into this image. Credentials resolve through the boto3 chain (the
# AgentCore Runtime task assumes the runtime IAM role automatically).
###############################################################################
ARG TARGETPLATFORM=linux/arm64

FROM --platform=linux/arm64 cgr.dev/chainguard/python:3.11-dev AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

USER root
RUN apk add --no-cache \
        build-base \
        gcc \
        gfortran \
        linux-headers \
        curl \
        git \
        postgresql-dev \
        postgresql-client

COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /usr/local/bin/uv

COPY pyproject.toml ./
COPY README.md ./
COPY aqp_platform_core ./aqp_platform_core
COPY aqp ./aqp
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./

###############################################################################
# Final stage — agent runtime. Installs the auth + cli + minimal extras
# needed for a single agent invocation. Heavy ML / Iceberg / Dagster
# extras stay out so the image cold-start is fast (AgentCore's
# 8-hour session limit is wall-clock; runtime image pull happens on
# every cold start so a leaner image = lower latency).
###############################################################################
FROM base AS agent

RUN uv pip install --system -e ./aqp_platform_core \
    && uv pip install --system -e ".[auth,otel,cli]"

RUN chown -R 65532:65532 /app
USER 65532:65532

EXPOSE 9100

ENTRYPOINT []
CMD ["python", "-m", "aqp.agents.agentcore_entrypoint"]
